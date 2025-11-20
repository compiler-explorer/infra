#!/usr/bin/env python3
"""CEFS consolidation and reconsolidation logic."""

from __future__ import annotations

import logging
import os
import shutil
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import humanfriendly
import yaml
from lib.cefs.deployment import (
    backup_and_symlink,
    check_temp_space_available,
    deploy_to_cefs_transactional,
    verify_symlinks_unchanged,
)
from lib.cefs.gc import check_if_symlink_references_image
from lib.cefs.models import ConsolidationCandidate
from lib.cefs.paths import (
    CEFSPaths,
    get_cefs_filename_for_image,
    get_cefs_mount_path,
    get_cefs_paths,
    get_directory_size,
    get_extraction_path_from_symlink,
)
from lib.cefs_manifest import (
    create_installable_manifest_entry,
    create_manifest,
    read_manifest_from_alongside,
    sanitize_path_for_filename,
    validate_manifest,
)
from lib.config import SquashfsConfig
from lib.installation_context import fix_permissions, is_windows
from lib.squashfs import create_squashfs_image, extract_squashfs_relocating_subdir

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExtractionResult:
    """Result of extracting a single squashfs image."""

    success: bool
    nfs_path: str
    subdir_name: str
    extracted_size: int = 0
    compressed_size: int = 0
    compression_ratio: float = 0.0
    is_partial: bool = False
    error: str | None = None


def _extract_single_squashfs(args: tuple[str, str, str, str | None, str, str]) -> ExtractionResult:
    """Worker function to extract a single squashfs image.

    Args are serialized as strings for pickling:
        unsquashfs_path, squashfs_path, extraction_dir, extraction_path, subdir_name, nfs_path

    Returns:
        Dictionary with extraction metrics and status
    """
    logger = logging.getLogger(__name__)
    unsquashfs_path, squashfs_path_str, extraction_dir_str, extraction_path_str, subdir_name, nfs_path_str = args

    squashfs_path = Path(squashfs_path_str)
    extraction_dir = Path(extraction_dir_str)
    extraction_path = Path(extraction_path_str) if extraction_path_str else None

    config = SquashfsConfig(
        mksquashfs_path="",
        unsquashfs_path=unsquashfs_path,
        compression="",
        compression_level=0,
    )

    try:
        compressed_size = squashfs_path.stat().st_size

        # Extract using helper that handles nested subdirectory extraction
        final_location = extraction_dir / subdir_name
        if extraction_path is not None:
            logger.info(
                "Partially extracting %s from %s (%s)",
                extraction_path,
                squashfs_path,
                humanfriendly.format_size(compressed_size, binary=True),
            )
        else:
            logger.info(
                "Extracting %s (%s)",
                squashfs_path,
                humanfriendly.format_size(compressed_size, binary=True),
            )

        extract_squashfs_relocating_subdir(config, squashfs_path, final_location, extraction_path)

        # Measure size at the extraction location
        extracted_size = get_directory_size(final_location)

        if extraction_path is not None:
            logger.info(
                "Partially extracted %s (%s from %s total image)",
                extraction_path,
                humanfriendly.format_size(extracted_size, binary=True),
                humanfriendly.format_size(compressed_size, binary=True),
            )
            return ExtractionResult(
                success=True,
                nfs_path=nfs_path_str,
                subdir_name=subdir_name,
                compressed_size=0,  # Don't count for partial extractions
                extracted_size=extracted_size,
                compression_ratio=0.0,
                is_partial=True,
            )

        compression_ratio = extracted_size / compressed_size if compressed_size > 0 else 0
        logger.info(
            "Extracted %s -> %s (%.1fx compression)",
            humanfriendly.format_size(compressed_size, binary=True),
            humanfriendly.format_size(extracted_size, binary=True),
            compression_ratio,
        )
        return ExtractionResult(
            success=True,
            nfs_path=nfs_path_str,
            subdir_name=subdir_name,
            compressed_size=compressed_size,
            extracted_size=extracted_size,
            compression_ratio=compression_ratio,
            is_partial=False,
        )
    except RuntimeError as e:
        logger.error("Failed to extract %s: %s", squashfs_path, e)
        return ExtractionResult(
            success=False,
            nfs_path=nfs_path_str,
            subdir_name=subdir_name,
            error=str(e),
        )


def create_consolidated_image(
    squashfs_config: SquashfsConfig,
    items: list[tuple[Path, Path, str, Path | None]],
    temp_dir: Path,
    output_path: Path,
    max_parallel_extractions: int | None = None,
) -> None:
    """Create a consolidated squashfs image from multiple CEFS items.

    Args:
        squashfs_config: SquashFsConfig object with tool paths and settings
        items: List of (nfs_path, squashfs_path, subdirectory_name, extraction_path) tuples
        temp_dir: Temporary directory for extraction
        output_path: Path for the consolidated squashfs image
        max_parallel_extractions: Maximum number of parallel extractions (default: CPU count - 1)

    Raises:
        RuntimeError: If consolidation fails
    """
    extraction_dir = temp_dir / "extract"
    extraction_dir.mkdir(parents=True, exist_ok=True)

    if max_parallel_extractions is None:
        max_parallel_extractions = max(1, (os.cpu_count() or 1) - 1)
    num_workers = min(max_parallel_extractions, len(items))

    _LOGGER.info("Starting parallel extraction with %d workers for %d items", num_workers, len(items))

    try:
        extraction_tasks = [
            (
                squashfs_config.unsquashfs_path,
                str(squashfs_path),
                str(extraction_dir),
                str(extraction_path) if extraction_path else None,
                subdir_name,
                str(nfs_path),
            )
            for nfs_path, squashfs_path, subdir_name, extraction_path in items
        ]

        total_compressed_size = 0
        total_extracted_size = 0
        partial_extractions_count = 0
        partial_extracted_size = 0
        failed_extractions = []

        with ProcessPoolExecutor(max_workers=num_workers) as executor:
            future_to_args = {executor.submit(_extract_single_squashfs, args): args for args in extraction_tasks}

            completed = 0
            for future in as_completed(future_to_args):
                completed += 1
                result = future.result()

                if not result.success:
                    failed_extractions.append(result)
                    _LOGGER.error(
                        "[%d/%d] Failed to extract %s: %s",
                        completed,
                        len(items),
                        result.subdir_name,
                        result.error or "Unknown error",
                    )
                    continue

                if result.is_partial:
                    partial_extractions_count += 1
                    partial_extracted_size += result.extracted_size
                else:
                    total_compressed_size += result.compressed_size

                total_extracted_size += result.extracted_size

                _LOGGER.info(
                    "[%d/%d] Completed extraction of %s",
                    completed,
                    len(items),
                    result.subdir_name,
                )

        if failed_extractions:
            raise RuntimeError(
                f"Failed to extract {len(failed_extractions)} of {len(items)} squashfs images: "
                + ", ".join(f.subdir_name for f in failed_extractions)
            )

        if partial_extractions_count > 0:
            _LOGGER.info(
                "Extraction summary: %d partial extractions (%s), %d full extractions",
                partial_extractions_count,
                humanfriendly.format_size(partial_extracted_size, binary=True),
                len(items) - partial_extractions_count,
            )

        if total_compressed_size > 0:
            full_extracted_size = total_extracted_size - partial_extracted_size
            compression_ratio = full_extracted_size / total_compressed_size if total_compressed_size > 0 else 0
            _LOGGER.info(
                "Full extractions: %s -> %s (%.1fx compression)",
                humanfriendly.format_size(total_compressed_size, binary=True),
                humanfriendly.format_size(full_extracted_size, binary=True),
                compression_ratio,
            )

        _LOGGER.info(
            "Total extracted data: %s",
            humanfriendly.format_size(total_extracted_size, binary=True),
        )

        # Fix permissions before creating consolidated squashfs to ensure all files are accessible
        if not is_windows():
            _LOGGER.info("Fixing permissions in extraction directory before consolidation")
            fix_permissions(extraction_dir)

        _LOGGER.info("Creating consolidated squashfs image at %s", output_path)
        create_squashfs_image(squashfs_config, extraction_dir, output_path)

        consolidated_size = output_path.stat().st_size

        _LOGGER.info("Consolidation complete:")
        _LOGGER.info(
            "  Final image size: %s",
            humanfriendly.format_size(consolidated_size, binary=True),
        )

        data_compression_ratio = total_extracted_size / consolidated_size if consolidated_size > 0 else 0
        _LOGGER.info(
            "  Data compression: %s -> %s (%.1fx)",
            humanfriendly.format_size(total_extracted_size, binary=True),
            humanfriendly.format_size(consolidated_size, binary=True),
            data_compression_ratio,
        )

        if total_compressed_size > 0:
            space_savings_ratio = total_compressed_size / consolidated_size if consolidated_size > 0 else 0
            _LOGGER.info(
                "  Space savings (full extractions only): %s -> %s (%.1fx reduction)",
                humanfriendly.format_size(total_compressed_size, binary=True),
                humanfriendly.format_size(consolidated_size, binary=True),
                space_savings_ratio,
            )

    finally:
        if extraction_dir.exists():
            shutil.rmtree(extraction_dir)
            _LOGGER.debug("Cleaned up extraction directory: %s", extraction_dir)


def update_symlinks_for_consolidation(
    unchanged_symlinks: list[Path],
    consolidated_filename: str,
    mount_point: Path,
    subdir_mapping: dict[Path, str],
    defer_cleanup: bool,
) -> None:
    """Update symlinks to point to consolidated CEFS mount.

    Args:
        unchanged_symlinks: List of symlinks that are safe to update
        consolidated_filename: Filename of the consolidated image (e.g., HASH_consolidated.sqfs)
        mount_point: CEFS mount point
        subdir_mapping: Mapping of nfs_path to subdirectory name in consolidated image
        defer_cleanup: If True, rename old .bak to .DELETE_ME_<timestamp> instead of deleting

    Raises:
        RuntimeError: If symlink update fails
    """
    for symlink_path in unchanged_symlinks:
        if symlink_path not in subdir_mapping:
            _LOGGER.warning("No subdirectory mapping for %s, skipping", symlink_path)
            continue

        subdir_name = subdir_mapping[symlink_path]
        new_target = get_cefs_mount_path(mount_point, consolidated_filename) / subdir_name

        try:
            backup_and_symlink(symlink_path, new_target, dry_run=False, defer_cleanup=defer_cleanup)
            _LOGGER.info("Updated symlink %s -> %s", symlink_path, new_target)
        except RuntimeError as e:
            raise RuntimeError(f"Failed to update symlink {symlink_path}: {e}") from e


def is_consolidated_image(image_path: Path) -> bool:
    """Check if a CEFS image is a consolidated image.

    Args:
        image_path: Path to the CEFS image

    Returns:
        True if this is a consolidated image, False otherwise
    """
    try:
        return bool((manifest := read_manifest_from_alongside(image_path)) and len(manifest["contents"]) > 1)
    except (OSError, yaml.YAMLError):
        return False


def calculate_image_usage(image_path: Path, image_references: dict[str, list[Path]], mount_point: Path) -> float:
    """Calculate usage percentage for a CEFS image.

    For individual images: 100% if referenced, 0% if not
    For consolidated images: percentage of subdirectories still referenced

    Args:
        image_path: Path to the CEFS image
        image_references: Dict mapping image stems to expected destinations
        mount_point: CEFS mount point

    Returns:
        Usage percentage (0.0 to 100.0)
    """
    filename_stem = image_path.stem
    expected_destinations = image_references.get(filename_stem, [])
    if not expected_destinations:
        return 0.0

    def is_destination_referenced(dest_path: Path) -> bool:
        full_path = Path(dest_path)
        main_ref = check_if_symlink_references_image(full_path, filename_stem, mount_point)
        bak_path = full_path.with_name(full_path.name + ".bak")
        bak_ref = check_if_symlink_references_image(bak_path, filename_stem, mount_point)
        return main_ref or bak_ref

    if len(expected_destinations) == 1:
        return 100.0 if is_destination_referenced(expected_destinations[0]) else 0.0

    referenced_count = sum(1 for dest in expected_destinations if is_destination_referenced(dest))
    return (referenced_count / len(expected_destinations)) * 100.0


def group_images_by_usage(partially_used: list[tuple[Path, float]]) -> dict[str, list[tuple[Path, float]]]:
    """Group partially used images by usage percentage ranges.

    Args:
        partially_used: List of (image_path, usage_percentage) tuples

    Returns:
        Dictionary mapping usage ranges to list of images in that range
    """
    ranges: dict[str, list[tuple[Path, float]]] = {"75-99%": [], "50-74%": [], "25-49%": [], "<25%": []}

    for image_path, usage in partially_used:
        if usage >= 75:
            ranges["75-99%"].append((image_path, usage))
        elif usage >= 50:
            ranges["50-74%"].append((image_path, usage))
        elif usage >= 25:
            ranges["25-49%"].append((image_path, usage))
        else:
            ranges["<25%"].append((image_path, usage))

    return ranges


def is_item_still_using_image(current_target: Path | None, image_path: Path, mount_point: Path) -> bool:
    """Check if a consolidated item is still using its original image.

    Args:
        current_target: The symlink target path (or None if not a symlink)
        image_path: Path to the CEFS image file
        mount_point: CEFS mount point (e.g., /cefs)

    Returns:
        True if the target points to this specific image
    """
    if not current_target or not str(current_target).startswith(str(mount_point) + "/"):
        return False

    # Get the filename stem from the symlink target
    # Format: {mount_point}/XX/FILENAME_STEM/... where FILENAME_STEM is like "abc123_consolidated"
    parts = current_target.parts
    mount_parts = mount_point.parts

    # Need at least: mount_point parts + hash_prefix + filename_stem
    if len(parts) < len(mount_parts) + 2:
        return False

    # The filename stem is at position: len(mount_parts) + 1
    # e.g., /cefs/ab/abc123_consolidated/tool1 -> abc123_consolidated is at index 3 when mount is /cefs (2 parts)
    return parts[len(mount_parts) + 1] == image_path.stem


def get_consolidated_item_status(
    content: dict, image_path: Path, current_target: Path | None, mount_point: Path
) -> str:
    """Get the status string for a single item in a consolidated image.

    Args:
        content: Manifest entry for the item
        image_path: Path to the consolidated image
        current_target: Current symlink target (or None)
        mount_point: CEFS mount point

    Returns:
        Formatted status string showing if item is still using the image
    """
    if "name" not in content:
        return ""

    if is_item_still_using_image(current_target, image_path, mount_point):
        return f"          ✓ {content['name']}"

    mount_str = str(mount_point) + "/"
    if current_target and str(current_target).startswith(mount_str):
        replacement_info = str(current_target).replace(mount_str, "")
        return f"          ✗ {content['name']} → replaced by {replacement_info}"
    return f"          ✗ {content['name']} → not in CEFS"


def should_reconsolidate_image(
    usage: float, size: int, efficiency_threshold: float, max_size_bytes: int, undersized_ratio: float
) -> tuple[bool, str]:
    """Determine if a consolidated image should be reconsolidated.

    Args:
        usage: Usage percentage (0-100)
        size: Image size in bytes
        efficiency_threshold: Minimum efficiency to keep (0.0-1.0)
        max_size_bytes: Maximum size for consolidated images
        undersized_ratio: Ratio to determine undersized images

    Returns:
        Tuple of (should_reconsolidate, reason_string)
    """
    if usage == 0:
        return False, ""
    if usage / 100.0 < efficiency_threshold:
        return True, f"low efficiency ({usage:.1f}%)"
    if size < max_size_bytes * undersized_ratio:
        return True, f"undersized ({humanfriendly.format_size(size, binary=True)})"
    return False, ""


def should_include_manifest_item(
    content: dict, image_path: Path, mount_point: Path, filter_: list[str]
) -> tuple[bool, Path | None]:
    """Check if a manifest item should be included for reconsolidation.

    Args:
        content: Manifest entry to check
        image_path: Path to the consolidated image
        mount_point: CEFS mount point
        filter_: Optional filter for selecting items

    Returns:
        Tuple of (should_include, target) where target is the main symlink target or None
    """
    if "destination" not in content or "name" not in content:
        raise ValueError(f"Malformed manifest entry missing required fields: {content}")

    dest_path = Path(content["destination"])

    # Only check the main symlink for reconsolidation, not backups
    # We reconsolidate items that are actively in use, not old backups
    if not dest_path.is_symlink():
        return False, None

    target = dest_path.resolve()

    # Check if this item is still referenced to this image
    if not is_item_still_using_image(target, image_path, mount_point):
        return False, target

    # Apply filter if provided
    if filter_ and not any(f in content["name"] for f in filter_):
        return False, target

    return True, target


def determine_extraction_path(targets: list[Path], image_path: Path, mount_point: Path) -> Path | None:
    """Determine the extraction path from symlink targets.

    Args:
        targets: List of symlink targets
        image_path: Path to the consolidated image
        mount_point: CEFS mount point

    Returns:
        Path within the consolidated image to extract from, or None to extract everything
    """
    for target in targets:
        if is_item_still_using_image(target, image_path, mount_point):
            if len(target.parts) > 4:
                return Path(*target.parts[4:])
            break
    return None


def extract_candidates_from_manifest(
    manifest: dict,
    image_path: Path,
    filter_: list[str],
    size: int,
    mount_point: Path,
) -> list[ConsolidationCandidate]:
    """Extract reconsolidation candidates from a consolidated image manifest.

    Args:
        manifest: Image manifest dictionary
        image_path: Path to the consolidated image
        filter_: Optional filter for selecting items
        size: Total size of the consolidated image
        mount_point: CEFS mount point

    Returns:
        List of consolidation candidates from this image
    """
    # Validate manifest before processing
    try:
        validate_manifest(manifest)
    except ValueError as e:
        _LOGGER.warning("Skipping reconsolidation from %s: %s", image_path, e)
        return []

    contents = manifest.get("contents", [])
    item_size = size // len(contents) if contents else 0  # Estimate size per item

    candidates = []
    for content in contents:
        should_include, target = should_include_manifest_item(content, image_path, mount_point, filter_)
        if not should_include:
            continue

        candidates.append(
            ConsolidationCandidate(
                name=content["name"],
                nfs_path=Path(content["destination"]),
                squashfs_path=image_path,
                extraction_path=determine_extraction_path([target] if target else [], image_path, mount_point),
                size=item_size,
                from_reconsolidation=True,
            )
        )

    return candidates


def pack_items_into_groups(
    items: list[ConsolidationCandidate], max_size_bytes: int, min_items: int
) -> list[list[ConsolidationCandidate]]:
    """Pack consolidation candidates into groups based on size and count constraints.

    Args:
        items: List of items to pack into groups
        max_size_bytes: Maximum size per group in bytes
        min_items: Minimum number of items per group

    Returns:
        List of groups, where each group is a list of ConsolidationCandidate
    """
    # Sort by name for deterministic packing
    sorted_items = sorted(items, key=lambda x: x.name)

    groups: list[list[ConsolidationCandidate]] = []
    current_group: list[ConsolidationCandidate] = []
    current_size = 0

    for item in sorted_items:
        if current_size + item.size > max_size_bytes and len(current_group) >= min_items:
            # Start new group
            groups.append(current_group)
            current_group = [item]
            current_size = item.size
        else:
            current_group.append(item)
            current_size += item.size

    # Add final group if it meets minimum criteria
    if len(current_group) >= min_items:
        groups.append(current_group)
    elif current_group:
        _LOGGER.info(
            "Final group has only %d items (< %d minimum), not consolidating",
            len(current_group),
            min_items,
        )

    return groups


def validate_space_requirements(groups: list[list[ConsolidationCandidate]], temp_dir: Path) -> tuple[int, int]:
    """Validate that there's enough space for consolidation.

    Args:
        groups: List of consolidation groups
        temp_dir: Temporary directory to check space for

    Returns:
        Tuple of (required_space, largest_group_size)

    Raises:
        RuntimeError: If insufficient space is available
    """
    if not groups:
        return 0, 0

    # Calculate space requirements
    largest_group_size = max(sum(item.size for item in group) for group in groups)
    required_temp_space = largest_group_size * 5  # Conservative multiplier for extraction/compression

    # Check available space
    temp_dir.mkdir(parents=True, exist_ok=True)
    if check_temp_space_available(temp_dir, required_temp_space):
        return required_temp_space, largest_group_size

    # Handle insufficient space
    if not temp_dir.exists():
        raise RuntimeError(f"Temp directory does not exist: {temp_dir}")

    stat = os.statvfs(temp_dir)
    available = stat.f_bavail * stat.f_frsize
    raise RuntimeError(
        f"Insufficient temp space. Required: {humanfriendly.format_size(required_temp_space, binary=True)}, "
        f"Available: {humanfriendly.format_size(available, binary=True)}"
    )


def prepare_consolidation_items(
    group: list[ConsolidationCandidate], mount_point: Path
) -> tuple[list[tuple[Path, Path, str, Path | None]], dict[Path, str]]:
    """Prepare items for consolidation by determining extraction paths and subdirectory names.

    Args:
        group: List of consolidation candidates
        mount_point: CEFS mount point

    Returns:
        Tuple of (items_for_consolidation, subdir_mapping)
        where items_for_consolidation is a list of (nfs_path, squashfs_path, subdir_name, extraction_path)
        and subdir_mapping maps nfs_path to subdir_name
    """
    items_for_consolidation = []
    subdir_mapping = {}

    for item in group:
        # Use the installable name as subdirectory name (sanitized for filesystem)
        subdir_name = sanitize_path_for_filename(Path(item.name))

        # For reconsolidation items, we already have the extraction path
        if item.from_reconsolidation:
            extraction_path = item.extraction_path
            _LOGGER.debug(
                "Reconsolidation item '%s': subdir_name='%s', extraction_path='%s'",
                item.name,
                subdir_name,
                extraction_path,
            )
        else:
            try:
                symlink_target = item.nfs_path.readlink()
                extraction_path = get_extraction_path_from_symlink(symlink_target, mount_point)
                _LOGGER.debug(
                    "For %s: symlink %s -> %s, extracting %s",
                    item.name,
                    item.nfs_path,
                    symlink_target,
                    extraction_path,
                )
            except OSError as e:
                _LOGGER.warning("Failed to read symlink %s: %s", item.nfs_path, e)
                continue

        items_for_consolidation.append((item.nfs_path, item.squashfs_path, subdir_name, extraction_path))
        subdir_mapping[item.nfs_path] = subdir_name

    return items_for_consolidation, subdir_mapping


def create_group_manifest(group: list[ConsolidationCandidate]) -> dict:
    """Create a manifest for a consolidation group.

    Args:
        group: List of consolidation candidates

    Returns:
        Manifest dictionary
    """
    contents = [create_installable_manifest_entry(item.name, item.nfs_path) for item in group]
    return create_manifest(
        operation="consolidate",
        description=f"Created through consolidation of {len(group)} items: " + ", ".join(item.name for item in group),
        contents=contents,
    )


def handle_symlink_updates(
    group: list[ConsolidationCandidate],
    symlink_snapshot: dict[Path, Path],
    filename: str,
    mount_point: Path,
    subdir_mapping: dict[Path, str],
    defer_backup_cleanup: bool,
) -> tuple[int, int]:
    """Handle symlink verification and updates for a consolidation group.

    Args:
        group: List of consolidation candidates
        symlink_snapshot: Snapshot of symlink states before consolidation
        filename: CEFS image filename
        mount_point: CEFS mount point
        subdir_mapping: Mapping of nfs_path to subdirectory name
        defer_backup_cleanup: Whether to defer cleanup of .bak symlinks

    Returns:
        Tuple of (updated_symlinks, skipped_symlinks)
    """
    # Verify symlinks haven't changed and update them
    group_symlinks = [item.nfs_path for item in group]
    group_snapshot = {k: v for k, v in symlink_snapshot.items() if k in group_symlinks}
    unchanged_symlinks, changed_symlinks = verify_symlinks_unchanged(group_snapshot)

    skipped_symlinks = 0
    updated_symlinks = 0

    if changed_symlinks:
        _LOGGER.warning("Skipping %d symlinks that changed during consolidation:", len(changed_symlinks))
        for symlink in changed_symlinks:
            _LOGGER.warning("  - %s", symlink)
        skipped_symlinks = len(changed_symlinks)

    if unchanged_symlinks:
        update_symlinks_for_consolidation(
            unchanged_symlinks,
            filename,
            mount_point,
            subdir_mapping,
            defer_backup_cleanup,
        )
        updated_symlinks = len(unchanged_symlinks)
        _LOGGER.info("Updated %d symlinks", updated_symlinks)

    return updated_symlinks, skipped_symlinks


def _perform_safety_check_and_rollback(
    group: list[ConsolidationCandidate],
    group_idx: int,
    find_installable_func: Callable[[str], Any],
    updated: int,
) -> int:
    """Perform safety check and rollback if needed.

    Returns:
        Updated count after any rollbacks
    """
    _LOGGER.info("Running post-consolidation safety checks for group %d", group_idx + 1)
    failed_items = []

    for item in group:
        try:
            installable = find_installable_func(item.name)
            if not installable.is_installed():
                failed_items.append((item.name, item.nfs_path))
                _LOGGER.error("Post-consolidation check failed: %s reports not installed", item.name)
        except ValueError as e:
            _LOGGER.error("Failed to find installable for validation: %s", e)
            failed_items.append((item.name, item.nfs_path))

    if not failed_items:
        return updated

    _LOGGER.warning("Found %d items failing is_installed() check, attempting rollback", len(failed_items))
    rollback_count = 0
    for name, symlink_path in failed_items:
        backup_path = Path(str(symlink_path) + ".bak")
        if not backup_path.exists():
            _LOGGER.warning("No backup found for %s, cannot rollback", name)
            continue

        try:
            if symlink_path.exists() or symlink_path.is_symlink():
                symlink_path.unlink()
            backup_path.rename(symlink_path)
            _LOGGER.info("Rolled back symlink for %s from backup", name)
            rollback_count += 1
            updated -= 1
        except OSError as e:
            _LOGGER.error("Failed to rollback symlink for %s: %s", name, e)

    if rollback_count < len(failed_items):
        _LOGGER.error("Failed to rollback %d items for group %d", len(failed_items) - rollback_count, group_idx + 1)

    return updated


def _deploy_consolidated_image(
    temp_consolidated_path: Path,
    cefs_paths: CEFSPaths,
    manifest: dict,
    group: list[ConsolidationCandidate],
    symlink_snapshot: dict[Path, Path],
    filename: str,
    mount_point: Path,
    subdir_mapping: dict[Path, str],
    defer_backup_cleanup: bool,
    group_idx: int,
    find_installable_func: Callable[[str], Any],
    dry_run: bool,
) -> tuple[int, int]:
    """Deploy consolidated image and update symlinks.

    Args:
        temp_consolidated_path: Path to temporary consolidated image
        cefs_paths: CEFS paths for the image
        manifest: Manifest for the consolidated image
        group: List of items in the group
        symlink_snapshot: Snapshot of symlink states
        filename: CEFS image filename
        mount_point: CEFS mount point
        subdir_mapping: Mapping of NFS paths to subdirectories
        defer_backup_cleanup: Whether to defer cleanup
        group_idx: Group index for logging
        find_installable_func: Function to find installables by exact name
        dry_run: Whether this is a dry run

    Returns:
        Tuple of (updated_symlinks, skipped_symlinks)
    """
    if cefs_paths.image_path.exists():
        _LOGGER.info("Consolidated image already exists: %s", cefs_paths.image_path)
        updated, skipped = handle_symlink_updates(
            group, symlink_snapshot, filename, mount_point, subdir_mapping, defer_backup_cleanup
        )

        if not dry_run and updated > 0:
            updated = _perform_safety_check_and_rollback(group, group_idx, find_installable_func, updated)

        return updated, skipped

    with deploy_to_cefs_transactional(
        temp_consolidated_path,
        cefs_paths.image_path,
        manifest,
        dry_run,
    ):
        updated, skipped = handle_symlink_updates(
            group, symlink_snapshot, filename, mount_point, subdir_mapping, defer_backup_cleanup
        )
        if updated:
            _LOGGER.info("Updated %d symlinks for group %d", updated, group_idx + 1)

        if not dry_run:
            updated = _perform_safety_check_and_rollback(group, group_idx, find_installable_func, updated)

        return updated, skipped


def process_consolidation_group(
    group: list[ConsolidationCandidate],
    group_idx: int,
    squashfs_config: Any,
    mount_point: Path,
    image_dir: Path,
    symlink_snapshot: dict[Path, Path],
    consolidation_dir: Path,
    defer_backup_cleanup: bool,
    max_parallel_extractions: int | None,
    find_installable_func: Callable[[str], Any],
    dry_run: bool = False,
) -> tuple[bool, int, int]:
    """Process a single consolidation group.

    Args:
        group: List of items to consolidate
        group_idx: Index of this group (for logging)
        squashfs_config: Squashfs configuration object
        mount_point: CEFS mount point
        image_dir: CEFS image directory
        symlink_snapshot: Snapshot of symlink states before consolidation
        consolidation_dir: Directory for consolidation temp files
        defer_backup_cleanup: Whether to defer cleanup of .bak symlinks
        max_parallel_extractions: Maximum parallel extractions
        find_installable_func: Function to find installables by exact name
        dry_run: Whether this is a dry run

    Returns:
        Tuple of (success, updated_symlinks, skipped_symlinks)
    """
    _LOGGER.info("Processing group %d (%d items)", group_idx + 1, len(group))

    group_temp_dir = consolidation_dir / "extract"

    try:
        # Create temp directory for this group
        group_temp_dir.mkdir(parents=True, exist_ok=True)

        # Prepare items for consolidation
        items_for_consolidation, subdir_mapping = prepare_consolidation_items(group, mount_point)

        if not items_for_consolidation:
            _LOGGER.warning("No valid items to consolidate in group %d", group_idx + 1)
            return False, 0, 0

        # Create manifest
        manifest = create_group_manifest(group)

        # Create temporary consolidated image
        temp_consolidated_path = group_temp_dir / "consolidated.sqfs"
        create_consolidated_image(
            squashfs_config,
            items_for_consolidation,
            group_temp_dir,
            temp_consolidated_path,
            max_parallel_extractions,
        )

        # Get CEFS paths for the image
        filename = get_cefs_filename_for_image(temp_consolidated_path, "consolidate")
        cefs_paths = get_cefs_paths(image_dir, mount_point, filename)

        # Deploy image and update symlinks
        updated_symlinks, skipped_symlinks = _deploy_consolidated_image(
            temp_consolidated_path,
            cefs_paths,
            manifest,
            group,
            symlink_snapshot,
            filename,
            mount_point,
            subdir_mapping,
            defer_backup_cleanup,
            group_idx,
            find_installable_func,
            dry_run,
        )

        return True, updated_symlinks, skipped_symlinks

    except RuntimeError as e:
        group_items = ", ".join(item.name for item in group)
        _LOGGER.error("Failed to consolidate group %d (%s): %s", group_idx + 1, group_items, e)
        _LOGGER.debug("Full error details:", exc_info=True)
        return False, 0, 0

    finally:
        # Clean up group temp directory
        if group_temp_dir.exists():
            shutil.rmtree(group_temp_dir)
