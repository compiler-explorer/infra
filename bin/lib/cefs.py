#!/usr/bin/env python3
"""CEFS (Compiler Explorer FileSystem) v2 utility functions."""

from __future__ import annotations

import datetime
import hashlib
import logging
import os
import shutil
import tempfile
import time
from collections.abc import Callable, Generator
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, NamedTuple

import humanfriendly
import yaml

from .cefs_manifest import (
    create_installable_manifest_entry,
    create_manifest,
    finalize_manifest,
    generate_cefs_filename,
    read_manifest_from_alongside,
    sanitize_path_for_filename,
    validate_manifest,
    write_manifest_inprogress,
)
from .config import SquashfsConfig
from .squashfs import create_squashfs_image, extract_squashfs_image

_LOGGER = logging.getLogger(__name__)

# Constants for NFS performance tuning
NFS_MAX_RECURSION_DEPTH = 3  # Limit depth when recursing on NFS to avoid performance issues


class FileWithAge(NamedTuple):
    """File path with age information."""

    path: Path
    age_seconds: float


@dataclass(frozen=True)
class CEFSPaths:
    """Container for CEFS image path and mount path."""

    image_path: Path
    mount_path: Path


@dataclass
class ConsolidationCandidate:
    """Represents an item that can be consolidated."""

    name: str
    nfs_path: Path
    squashfs_path: Path
    size: int
    extraction_path: Path = Path(".")
    from_reconsolidation: bool = False


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


def get_cefs_image_path(image_dir: Path, filename: str) -> Path:
    """Get the full CEFS image path for a given filename.

    Args:
        image_dir: Base image directory (e.g., Path("/efs/cefs-images"))
        filename: Complete filename with descriptive suffix

    Returns:
        Full path to the CEFS image file (e.g., /efs/cefs-images/a1/a1b2c3d4....sqfs)
    """
    return image_dir / filename[:2] / filename


def get_cefs_mount_path(mount_point: Path, filename: str) -> Path:
    """Get the full CEFS mount target path for a given hash.

    Args:
        mount_point: Base mount point (e.g., Path("/cefs"))
        filename: Complete filename with descriptive suffix

    Returns:
        Full path to the CEFS mount target (e.g., {mount_point}/a1/a1b2c3d4...)
    """
    return mount_point / filename[:2] / Path(filename).with_suffix("")


def get_cefs_paths(image_dir: Path, mount_point: Path, filename: str) -> CEFSPaths:
    """Get both CEFS image path and mount path for a given filename.

    Args:
        image_dir: Base image directory (e.g., Path("/efs/cefs-images"))
        mount_point: Base mount point (e.g., Path("/cefs"))
        filename: Complete filename with descriptive suffix

    Returns:
        CEFSPaths containing both image_path and mount_path
    """
    return CEFSPaths(
        image_path=get_cefs_image_path(image_dir, filename),
        mount_path=get_cefs_mount_path(mount_point, filename),
    )


def calculate_squashfs_hash(squashfs_path: Path) -> str:
    """Calculate SHA256 hash of squashfs image using Python hashlib."""
    sha256_hash = hashlib.sha256()
    file_size = squashfs_path.stat().st_size
    _LOGGER.debug("Calculating hash for %s (size: %d bytes)", squashfs_path, file_size)
    with open(squashfs_path, "rb") as f:
        for chunk in iter(lambda: f.read(16 * 1024 * 1024), b""):
            sha256_hash.update(chunk)
    full_hash = sha256_hash.hexdigest()
    truncated_hash = full_hash[:24]
    _LOGGER.debug("Hash for %s: full=%s, truncated=%s", squashfs_path, full_hash, truncated_hash)
    return truncated_hash


def get_cefs_filename_for_image(squashfs_path: Path, operation: str, path: Path | None = None) -> str:
    """Generate CEFS filename by calculating hash and adding suffix.

    Combines hash calculation and filename generation into a single operation.

    Args:
        squashfs_path: Path to squashfs image to hash
        operation: Operation type ("install", "convert", "consolidate")
        path: Optional path for suffix generation

    Returns:
        Generated filename with hash and descriptive suffix

    Raises:
        OSError: If unable to read the squashfs file
    """
    hash_value = calculate_squashfs_hash(squashfs_path)
    return generate_cefs_filename(hash_value, operation, path)


def detect_nfs_state(nfs_path: Path) -> str:
    """Detect current state: 'symlink', 'directory', or 'missing'."""
    if nfs_path.is_symlink():
        return "symlink"
    elif nfs_path.exists():
        return "directory"
    else:
        return "missing"


def validate_cefs_mount_point(mount_point: Path) -> bool:
    """Validate that CEFS mount point is accessible.

    Args:
        mount_point: CEFS mount point path (e.g., Path("/cefs"))

    Returns:
        True if mount point is accessible, False otherwise
    """
    mount_path = mount_point

    if not mount_path.exists():
        _LOGGER.error("CEFS mount point does not exist: %s", mount_point)
        return False

    if not mount_path.is_dir():
        _LOGGER.error("CEFS mount point is not a directory: %s", mount_point)
        return False

    # Try to access the mount point (this will trigger autofs if configured)
    try:
        list(mount_path.iterdir())
        return True
    except PermissionError:
        _LOGGER.error("No permission to access CEFS mount point: %s", mount_point)
        return False
    except OSError as e:
        _LOGGER.error("Cannot access CEFS mount point %s: %s", mount_point, e)
        return False


def get_directory_size(directory: Path) -> int:
    """Calculate total size of a directory tree in bytes.

    Args:
        directory: Directory to measure

    Returns:
        Total size in bytes
    """
    total_size = 0
    try:
        for item in directory.rglob("*"):
            if item.is_file() and not item.is_symlink():
                total_size += item.stat().st_size
    except OSError as e:
        _LOGGER.warning("Error calculating directory size for %s: %s", directory, e)
    return total_size


def copy_to_cefs_atomically(source_path: Path, cefs_image_path: Path) -> None:
    """Copy a file to CEFS images directory using atomic rename.

    Creates a uniquely named temp file and atomically renames it to ensure
    we never have truncated .sqfs files in the CEFS directory.

    Args:
        source_path: Source squashfs image to copy
        cefs_image_path: Target path in CEFS images directory

    Raises:
        Exception: If copy fails (temp file is cleaned up)
    """
    _LOGGER.info("Copying %s to %s", source_path, cefs_image_path)
    cefs_image_path.parent.mkdir(parents=True, exist_ok=True)

    # SAFETY: Create uniquely named temp file in same directory for atomic rename
    # This ensures that partially copied files never have the .sqfs extension
    # and thus can never be mistaken for complete images by GC or other operations
    with tempfile.NamedTemporaryFile(
        dir=cefs_image_path.parent, suffix=".tmp", prefix="cefs_", delete=False
    ) as temp_file:
        temp_path = Path(temp_file.name)
        with open(source_path, "rb") as source_file:
            shutil.copyfileobj(source_file, temp_file, length=1024 * 1024)
    try:
        # Atomic rename - only complete files get .sqfs extension
        # On Linux, rename() is atomic within the same filesystem
        temp_path.replace(cefs_image_path)
    except Exception:
        # Clean up temp file on any failure
        temp_path.unlink(missing_ok=True)
        raise


@contextmanager
def deploy_to_cefs_transactional(
    source_path: Path, cefs_image_path: Path, manifest: dict, dry_run: bool = False
) -> Generator[Path, None, None]:
    """Deploy an image to CEFS with automatic manifest finalization.

    This context manager ensures the manifest is properly finalized on success,
    or left as .inprogress on failure for debugging. This prevents the common
    mistake of forgetting to call finalize_manifest().

    Uses .yaml.inprogress pattern to prevent race conditions:
    1. Copy squashfs image atomically
    2. Write manifest as .yaml.inprogress (operation incomplete)
    3. Caller creates symlinks within the context
    4. Manifest is automatically finalized on successful exit

    Args:
        source_path: Source squashfs image to deploy
        cefs_image_path: Target path in CEFS images directory
        manifest: Manifest dictionary to write alongside the image
        dry_run: If True, skip actual deployment (for testing)

    Yields:
        Path to the deployed CEFS image

    Raises:
        Exception: If deployment fails (manifest remains .inprogress)

    Example:
        with deploy_to_cefs_transactional(source, target, manifest, dry_run) as image_path:
            create_symlinks(...)
            # Manifest is automatically finalized here on success
    """
    if dry_run:
        _LOGGER.info("DRY RUN: Would deploy %s to %s", source_path, cefs_image_path)
        yield cefs_image_path
        return

    # Deploy the image and write .inprogress manifest
    copy_to_cefs_atomically(source_path, cefs_image_path)
    write_manifest_inprogress(manifest, cefs_image_path)

    finalized = False
    try:
        yield cefs_image_path
        # If we get here, the context block completed successfully
        finalized = True
    finally:
        if not finalized:
            _LOGGER.warning("Leaving manifest as .inprogress for debugging: %s", cefs_image_path)
        else:
            try:
                finalize_manifest(cefs_image_path)
                _LOGGER.debug("Finalized manifest for %s", cefs_image_path)
            except Exception as e:
                _LOGGER.error("Failed to finalize manifest for %s: %s", cefs_image_path, e)
                # Note: We don't re-raise here because the main operation succeeded


def backup_and_symlink(nfs_path: Path, cefs_target: Path, dry_run: bool, defer_cleanup: bool) -> None:
    """Backup NFS directory and create CEFS symlink with rollback on failure.

    Args:
        nfs_path: Path to the NFS directory to backup and replace with symlink
        cefs_target: Target path for the CEFS symlink
        dry_run: If True, only log what would be done
        defer_cleanup: If True, rename old .bak to .DELETE_ME_<timestamp> instead of deleting
    """
    backup_path = nfs_path.with_name(nfs_path.name + ".bak")

    if dry_run:
        _LOGGER.info("Would backup %s to %s", nfs_path, backup_path)
        _LOGGER.info("Would create symlink %s -> %s", nfs_path, cefs_target)
        return

    try:
        # Handle old backup if it exists
        if backup_path.exists():
            if defer_cleanup:
                # Rename to .DELETE_ME_<timestamp> for later cleanup
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                delete_me_path = nfs_path.with_name(f"{nfs_path.name}.DELETE_ME_{timestamp}")
                backup_path.rename(delete_me_path)
                _LOGGER.info("Renamed old backup %s to %s for deferred cleanup", backup_path, delete_me_path)
            else:
                # Original behavior: delete immediately
                if backup_path.is_dir():
                    shutil.rmtree(backup_path)
                else:
                    backup_path.unlink()

        # Backup current directory (or symlink) if it exists. Follow symlinks=False here to account for broken symlinks
        if nfs_path.exists(follow_symlinks=False):
            nfs_path.rename(backup_path)
            _LOGGER.info("Backed up %s to %s", nfs_path, backup_path)

        # Create symlink
        nfs_path.symlink_to(cefs_target, target_is_directory=True)
        _LOGGER.info("Created symlink %s -> %s", nfs_path, cefs_target)

    except OSError as e:
        # Rollback on failure
        if backup_path.exists():
            nfs_path.unlink(missing_ok=True)
            backup_path.rename(nfs_path)
            _LOGGER.error("Rollback: restored %s from backup", nfs_path)
        raise RuntimeError(f"Failed to create symlink: {e}") from e


def has_enough_space(available_bytes: int, required_bytes: int) -> bool:
    """Pure function to check if available space meets requirements.

    Args:
        available_bytes: Available space in bytes
        required_bytes: Required space in bytes

    Returns:
        True if enough space is available
    """
    return available_bytes >= required_bytes


def check_temp_space_available(temp_dir: Path, required_bytes: int) -> bool:
    """Check if temp directory has enough space for consolidation.

    Args:
        temp_dir: Directory to check space for
        required_bytes: Required space in bytes

    Returns:
        True if enough space is available
    """
    try:
        stat = os.statvfs(temp_dir)
        available_bytes = stat.f_bavail * stat.f_frsize
        _LOGGER.debug("Available space: %d bytes, required: %d bytes", available_bytes, required_bytes)
        return has_enough_space(available_bytes, required_bytes)
    except OSError as e:
        _LOGGER.error("Failed to check disk space for %s: %s", temp_dir, e)
        return False


def snapshot_symlink_targets(symlink_paths: list[Path]) -> dict[Path, Path]:
    """Snapshot current symlink targets for race condition detection.

    Args:
        symlink_paths: List of symlink paths to snapshot

    Returns:
        Dictionary mapping symlink path to current target
    """
    snapshot = {}
    for symlink_path in symlink_paths:
        try:
            if symlink_path.is_symlink():
                snapshot[symlink_path] = symlink_path.readlink()
                _LOGGER.debug("Snapshotted %s -> %s", symlink_path, snapshot[symlink_path])
        except OSError as e:
            _LOGGER.warning("Failed to read symlink %s: %s", symlink_path, e)
    return snapshot


def verify_symlinks_unchanged(snapshot: dict[Path, Path]) -> tuple[list[Path], list[Path]]:
    """Verify symlinks haven't changed since snapshot.

    Args:
        snapshot: Dictionary of symlink path to expected target

    Returns:
        Tuple of (unchanged_symlinks, changed_symlinks)
    """
    unchanged = []
    changed = []

    for symlink_path, expected_target in snapshot.items():
        try:
            if symlink_path.is_symlink():
                current_target = symlink_path.readlink()
                if current_target == expected_target:
                    unchanged.append(symlink_path)
                else:
                    changed.append(symlink_path)
                    _LOGGER.warning(
                        "Symlink changed during consolidation: %s (was: %s, now: %s)",
                        symlink_path,
                        expected_target,
                        current_target,
                    )
            else:
                changed.append(symlink_path)
                _LOGGER.warning("Symlink no longer exists: %s", symlink_path)
        except OSError as e:
            changed.append(symlink_path)
            _LOGGER.warning("Failed to read symlink %s: %s", symlink_path, e)

    return unchanged, changed


def _extract_single_squashfs(args: tuple[str, str, str, str | None, str, str]) -> ExtractionResult:
    """Worker function to extract a single squashfs image.

    Args are serialized as strings for pickling:
        unsquashfs_path, squashfs_path, subdir_path, extraction_path, subdir_name, nfs_path

    Returns:
        Dictionary with extraction metrics and status
    """
    # Set up logging for worker process
    logger = logging.getLogger(__name__)

    # Unpack and convert arguments back from strings
    unsquashfs_path, squashfs_path_str, subdir_path_str, extraction_path_str, subdir_name, nfs_path_str = args

    squashfs_path = Path(squashfs_path_str)
    subdir_path = Path(subdir_path_str)
    extraction_path = Path(extraction_path_str) if extraction_path_str else None

    # Create minimal config for extraction
    config = SquashfsConfig(
        mksquashfs_path="",  # Not needed for extraction
        unsquashfs_path=unsquashfs_path,
        compression="",  # Not needed for extraction
        compression_level=0,  # Not needed for extraction
    )

    try:
        compressed_size = squashfs_path.stat().st_size

        # Check if this is a partial extraction
        is_partial_extraction = extraction_path is not None and extraction_path != Path(".")

        if is_partial_extraction:
            logger.info(
                "Partially extracting %s from %s (%s) to %s",
                extraction_path,
                squashfs_path,
                humanfriendly.format_size(compressed_size, binary=True),
                subdir_path,
            )
        else:
            logger.info(
                "Extracting %s (%s) to %s",
                squashfs_path,
                humanfriendly.format_size(compressed_size, binary=True),
                subdir_path,
            )

        extract_squashfs_image(config, squashfs_path, subdir_path, extraction_path)

        # Measure extracted size
        extracted_size = get_directory_size(subdir_path)

        if is_partial_extraction:
            # For partial extractions, don't calculate misleading compression ratios
            logger.info(
                "Partially extracted %s (%s from %s total image)",
                extraction_path,
                humanfriendly.format_size(extracted_size, binary=True),
                humanfriendly.format_size(compressed_size, binary=True),
            )
            # Don't include compressed_size in stats for partial extractions
            return ExtractionResult(
                success=True,
                nfs_path=nfs_path_str,
                subdir_name=subdir_name,
                compressed_size=0,  # Don't count for partial extractions
                extracted_size=extracted_size,
                compression_ratio=0.0,
                is_partial=True,
            )
        else:
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
    except Exception as e:
        logger.error("Failed to extract %s: %s", squashfs_path, e)
        return ExtractionResult(
            success=False,
            nfs_path=nfs_path_str,
            subdir_name=subdir_name,
            error=str(e),
        )


def create_consolidated_image(
    squashfs_config: SquashfsConfig,
    items: list[tuple[Path, Path, str, Path]],
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
        max_parallel_extractions: Maximum number of parallel extractions (default: CPU count)

    Raises:
        RuntimeError: If consolidation fails
    """
    extraction_dir = temp_dir / "extract"
    extraction_dir.mkdir(parents=True, exist_ok=True)

    # Determine number of workers
    if max_parallel_extractions is None:
        max_parallel_extractions = os.cpu_count() or 1
    num_workers = min(max_parallel_extractions, len(items))

    _LOGGER.info("Starting parallel extraction with %d workers for %d items", num_workers, len(items))

    try:
        # Prepare extraction tasks (serialize paths as strings for pickling)
        extraction_tasks = []
        for nfs_path, squashfs_path, subdir_name, extraction_path in items:
            subdir_path = extraction_dir / subdir_name
            args = (
                squashfs_config.unsquashfs_path,
                str(squashfs_path),
                str(subdir_path),
                str(extraction_path) if extraction_path else None,
                subdir_name,
                str(nfs_path),
            )
            extraction_tasks.append(args)

        # Extract squashfs images in parallel
        total_compressed_size = 0
        total_extracted_size = 0
        partial_extractions_count = 0
        partial_extracted_size = 0
        failed_extractions = []

        with ProcessPoolExecutor(max_workers=num_workers) as executor:
            # Submit all extraction tasks
            future_to_args = {executor.submit(_extract_single_squashfs, args): args for args in extraction_tasks}

            # Process results as they complete
            completed = 0
            for future in as_completed(future_to_args):
                completed += 1
                result = future.result()

                if result.success:
                    if result.is_partial:
                        # Track partial extractions separately
                        partial_extractions_count += 1
                        partial_extracted_size += result.extracted_size
                    else:
                        # Only count full extractions for compression stats
                        total_compressed_size += result.compressed_size

                    # Always add extracted size for total
                    total_extracted_size += result.extracted_size

                    _LOGGER.info(
                        "[%d/%d] Completed extraction of %s",
                        completed,
                        len(items),
                        result.subdir_name,
                    )
                else:
                    failed_extractions.append(result)
                    _LOGGER.error(
                        "[%d/%d] Failed to extract %s: %s",
                        completed,
                        len(items),
                        result.subdir_name,
                        result.error or "Unknown error",
                    )

        # Check for failures
        if failed_extractions:
            raise RuntimeError(
                f"Failed to extract {len(failed_extractions)} of {len(items)} squashfs images: "
                + ", ".join(f.subdir_name for f in failed_extractions)
            )

        # Log total extraction summary
        if partial_extractions_count > 0:
            _LOGGER.info(
                "Extraction summary: %d partial extractions (%s), %d full extractions",
                partial_extractions_count,
                humanfriendly.format_size(partial_extracted_size, binary=True),
                len(items) - partial_extractions_count,
            )

        if total_compressed_size > 0:
            # Only show compression ratio for full extractions
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

        # Create consolidated squashfs image
        _LOGGER.info("Creating consolidated squashfs image at %s", output_path)
        create_squashfs_image(squashfs_config, extraction_dir, output_path)

        # Log final consolidation compression ratio
        consolidated_size = output_path.stat().st_size

        # Calculate meaningful compression ratios
        _LOGGER.info("Consolidation complete:")
        _LOGGER.info(
            "  Final image size: %s",
            humanfriendly.format_size(consolidated_size, binary=True),
        )

        # Compression of extracted data (this is the real compression achieved)
        data_compression_ratio = total_extracted_size / consolidated_size if consolidated_size > 0 else 0
        _LOGGER.info(
            "  Data compression: %s -> %s (%.1fx)",
            humanfriendly.format_size(total_extracted_size, binary=True),
            humanfriendly.format_size(consolidated_size, binary=True),
            data_compression_ratio,
        )

        # If we have full extractions, show space savings
        if total_compressed_size > 0:
            space_savings_ratio = total_compressed_size / consolidated_size if consolidated_size > 0 else 0
            _LOGGER.info(
                "  Space savings (full extractions only): %s -> %s (%.1fx reduction)",
                humanfriendly.format_size(total_compressed_size, binary=True),
                humanfriendly.format_size(consolidated_size, binary=True),
                space_savings_ratio,
            )

    finally:
        # Clean up extraction directory
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
        # New target: {mount_point}/XX/HASH_consolidated/subdir_name
        new_target = get_cefs_mount_path(mount_point, consolidated_filename) / subdir_name

        try:
            backup_and_symlink(symlink_path, new_target, dry_run=False, defer_cleanup=defer_cleanup)
            _LOGGER.info("Updated symlink %s -> %s", symlink_path, new_target)
        except RuntimeError as e:
            raise RuntimeError(f"Failed to update symlink {symlink_path}: {e}") from e


def parse_cefs_target(cefs_target: Path, cefs_image_dir: Path, mount_point: Path) -> tuple[Path, bool]:
    """Parse CEFS symlink target and return image path and consolidation status.

    Args:
        cefs_target: The symlink target (e.g., {mount_point}/XX/HASH or {mount_point}/XX/HASH/subdir)
        cefs_image_dir: Base directory for CEFS images (e.g., /efs/cefs-images)
        mount_point: CEFS mount point (e.g., /cefs)

    Returns:
        Tuple of (cefs_image_path, is_already_consolidated)

    Raises:
        ValueError: If the CEFS target format is invalid

    Examples:
        >>> parse_cefs_target(Path("/cefs/9d/9da642f654bc890a12345678"), Path("/efs/cefs-images"), Path("/cefs"))
        (Path("/efs/cefs-images/9d/9da642f654bc890a12345678_gcc.sqfs"), False)

        >>> parse_cefs_target(Path("/cefs/ab/abcdef1234567890abcdef12/gcc-4.5"), Path("/efs/cefs-images"), Path("/cefs"))
        (Path("/efs/cefs-images/ab/abcdef1234567890abcdef12_consolidated.sqfs"), True)
    """
    parts = cefs_target.parts
    mount_parts = mount_point.parts
    # Expected: mount_point parts + ('XX', 'HASH', ...) for {mount_point}/XX/HASH/...

    # Check that target starts with mount_point
    if len(parts) < len(mount_parts) + 2:  # Need at least mount_point + XX + HASH
        raise ValueError(f"Invalid CEFS target format: {cefs_target}")

    # Verify the target starts with the mount point
    if parts[: len(mount_parts)] != mount_parts:
        raise ValueError(f"CEFS target must start with {mount_point}: {cefs_target}")

    # Get XX and HASH parts after the mount point
    hash_prefix = parts[len(mount_parts)]  # XX
    hash = parts[len(mount_parts) + 1]  # 24-char hash

    image_dir_subdir = cefs_image_dir / hash_prefix
    matching_files = list(image_dir_subdir.glob(f"{hash}*.sqfs"))

    if not matching_files:
        raise ValueError(f"No CEFS image found for hash {hash} in {image_dir_subdir}")

    cefs_image_path = matching_files[0]

    # If there are more parts after the hash, it's already consolidated
    is_already_consolidated = len(parts) > len(mount_parts) + 2

    return cefs_image_path, is_already_consolidated


def describe_cefs_image(filename: str, cefs_mount_point: Path) -> list[str]:
    """Get top-level entries from a CEFS image by triggering autofs mount.

    Args:
        filename: The CEFS hash filename to describe
        cefs_mount_point: Base CEFS mount point

    Returns:
        List of top-level entry names in the CEFS image
    """
    cefs_path = get_cefs_mount_path(cefs_mount_point, filename)
    try:
        return [entry.name for entry in cefs_path.iterdir()]
    except OSError as e:
        _LOGGER.warning("Could not list contents of %s: %s", cefs_path, e)
        return []


class CEFSState:
    """Track CEFS images and their references for garbage collection using manifests."""

    def __init__(self, nfs_dir: Path, cefs_image_dir: Path, mount_point: Path):
        """Initialize CEFS state tracker.

        Args:
            nfs_dir: Base NFS directory (e.g., /opt/compiler-explorer)
            cefs_image_dir: CEFS images directory (e.g., /efs/cefs-images)
            mount_point: CEFS mount point (e.g., /cefs)
        """
        self.nfs_dir = nfs_dir
        self.cefs_image_dir = cefs_image_dir
        self.mount_point = mount_point
        self.all_cefs_images: dict[str, Path] = {}  # filename_stem -> image_path
        self.image_references: dict[str, list[Path]] = {}  # filename_stem -> list of expected symlink destinations
        self.referenced_images: set[str] = set()  # Set of filename_stems that have valid symlinks
        self.inprogress_images: list[Path] = []  # List of .yaml.inprogress files found
        self.broken_images: list[Path] = []  # Images without .yaml or .yaml.inprogress

    def scan_cefs_images_with_manifests(self) -> None:
        """Scan all CEFS images and read their manifests to determine expected references.

        CRITICAL: Images with .yaml.inprogress manifests are tracked but NEVER eligible for GC.
        """
        if not self.cefs_image_dir.exists():
            _LOGGER.warning("CEFS images directory does not exist: %s", self.cefs_image_dir)
            return

        for subdir in self.cefs_image_dir.iterdir():
            if subdir.is_dir():
                # First check for .yaml.inprogress files (incomplete operations)
                for inprogress_file in subdir.glob("*.yaml.inprogress"):
                    self.inprogress_images.append(inprogress_file)
                    _LOGGER.warning("Found in-progress manifest: %s", inprogress_file)

                for image_file in subdir.glob("*.sqfs"):
                    # Store by filename stem (includes hash and suffix)
                    filename_stem = image_file.stem

                    # SAFETY: Check if this image has an .yaml.inprogress file indicating incomplete operation
                    # This prevents deletion of images that are being installed/converted/consolidated
                    # even if the operation is taking a long time or has failed partway through
                    inprogress_path = Path(str(image_file.with_suffix(".yaml")) + ".inprogress")
                    if inprogress_path.exists():
                        # Skip this image - it has an incomplete operation
                        _LOGGER.info("Skipping image with in-progress operation: %s", image_file)
                        # Mark it as referenced so it won't be deleted
                        self.referenced_images.add(filename_stem)
                        continue

                    # Check for .yaml manifest
                    manifest_path = image_file.with_suffix(".yaml")
                    if not manifest_path.exists():
                        # No .yaml and no .yaml.inprogress - this is a broken image
                        self.broken_images.append(image_file)
                        _LOGGER.error(
                            "BROKEN IMAGE: %s has no manifest or inprogress marker - needs investigation", image_file
                        )
                        # Do NOT add to all_cefs_images or image_references
                        continue

                    self.all_cefs_images[filename_stem] = image_file

                    # Try to read manifest to get expected destinations
                    try:
                        manifest = read_manifest_from_alongside(image_file)
                        if manifest and "contents" in manifest:
                            destinations = []
                            for content in manifest["contents"]:
                                if "destination" in content:
                                    dest_path = Path(content["destination"])
                                    destinations.append(dest_path)
                            self.image_references[filename_stem] = destinations
                            _LOGGER.debug("Image %s expects %d symlinks", filename_stem, len(destinations))
                        else:
                            # Manifest exists but has no contents or is malformed
                            self.image_references[filename_stem] = []
                            _LOGGER.warning("Manifest for %s has no contents", filename_stem)
                    except Exception as e:
                        _LOGGER.warning("Failed to read manifest for %s: %s", image_file, e)
                        self.image_references[filename_stem] = []

    def check_symlink_references(self) -> None:
        """Check if expected symlinks exist and point to the correct CEFS images."""
        for filename_stem, expected_destinations in self.image_references.items():
            if not expected_destinations:
                # Image has empty manifest - this is an error condition like missing manifest
                image_path = self.all_cefs_images.get(filename_stem)
                if image_path:
                    self.broken_images.append(image_path)
                    # Mark as referenced so it won't be deleted
                    self.referenced_images.add(filename_stem)
                    _LOGGER.error("BROKEN IMAGE: %s has empty manifest - needs investigation", image_path)
                continue

            # Check if any expected symlink points to this image
            for dest_path in expected_destinations:
                if self._check_symlink_points_to_image(dest_path, filename_stem):
                    self.referenced_images.add(filename_stem)
                    break  # At least one valid reference found

    def _check_symlink_points_to_image(self, dest_path: Path, filename_stem: str) -> bool:
        """Check if a symlink at dest_path points to the given CEFS image.

        CRITICAL: Also checks .bak symlinks to protect rollback capability.

        Args:
            dest_path: Expected destination path for symlink
            filename_stem: The filename stem (hash + suffix) of the CEFS image

        Returns:
            True if symlink exists and points to this image (either main or .bak)
        """
        full_path = dest_path if dest_path.is_absolute() else self.nfs_dir / dest_path.relative_to(Path("/"))

        # Check main symlink
        if self._check_single_symlink(full_path, filename_stem):
            return True

        # CRITICAL: Also check .bak symlink to protect rollback capability
        # Users rely on 'ce cefs rollback' which swaps .bak with main symlink
        # If we deleted the image referenced by .bak, rollback would fail catastrophically
        bak_path = full_path.with_name(full_path.name + ".bak")
        if self._check_single_symlink(bak_path, filename_stem):
            _LOGGER.debug("Found reference via .bak symlink: %s", bak_path)
            return True

        return False

    def _check_single_symlink(self, symlink_path: Path, filename_stem: str) -> bool:
        """Check if a single symlink points to the given CEFS image.

        Args:
            symlink_path: Path to check
            filename_stem: The filename stem (hash + suffix) of the CEFS image

        Returns:
            True if symlink exists and points to this image
        """
        if symlink_path.is_symlink():
            try:
                target = symlink_path.readlink()
                if str(target).startswith(str(self.mount_point) + "/"):
                    # Extract the hash/filename from the symlink target
                    # Format: {mount_point}/XX/HASH_suffix or {mount_point}/XX/HASH_suffix/subdir
                    target_path = Path(target)
                    mount_parts = self.mount_point.parts
                    target_parts = target_path.parts
                    if len(target_parts) >= len(mount_parts) + 2:
                        # The filename part is at the position after mount_point + XX
                        target_filename = target_parts[len(mount_parts) + 1]
                        # Check if this matches our image's filename stem
                        if target_filename == filename_stem:
                            _LOGGER.debug("Found valid symlink: %s -> %s", symlink_path, target)
                            return True
            except OSError as e:
                _LOGGER.error(
                    "Could not read symlink %s: %s - assuming it references the image to be safe",
                    symlink_path,
                    e,
                )
                return True  # When in doubt, keep the image
        return False

    def is_image_referenced(self, filename_stem: str) -> bool:
        """Check if an image is referenced by any symlink.

        Args:
            filename_stem: The image filename stem

        Returns:
            True if any symlink references this image

        Raises:
            ValueError: If image has no manifest data (shouldn't happen for valid images)
        """
        if filename_stem not in self.image_references:
            # This is an error - all valid images should have manifest data
            raise ValueError(f"Image {filename_stem} has no manifest data - this should not happen")

        for dest_path in self.image_references[filename_stem]:
            if self._check_symlink_points_to_image(dest_path, filename_stem):
                return True
        return False

    def find_unreferenced_images(self) -> list[Path]:
        """Find all CEFS images that are not referenced by any symlink.

        Returns:
            List of Path objects for unreferenced CEFS images
        """
        unreferenced = []
        for filename_stem, image_path in self.all_cefs_images.items():
            if filename_stem not in self.referenced_images:
                unreferenced.append(image_path)
        return unreferenced

    def get_summary(self) -> GCSummary:
        """Get summary statistics for reporting.

        Returns:
            GCSummary with statistics
        """
        unreferenced_images = self.find_unreferenced_images()
        space_to_reclaim = 0

        for image_path in unreferenced_images:
            try:
                space_to_reclaim += image_path.stat().st_size
            except OSError:
                _LOGGER.warning("Could not stat unreferenced image: %s", image_path)

        return GCSummary(
            total_images=len(self.all_cefs_images),
            referenced_images=len(self.referenced_images),
            unreferenced_images=len(unreferenced_images),
            space_to_reclaim=space_to_reclaim,
        )

    def get_usage_stats(self) -> ImageUsageStats:
        """Get detailed usage statistics for all CEFS images.

        Returns:
            ImageUsageStats with detailed usage breakdown
        """
        return get_consolidated_image_usage_stats(self)

    def _analyze_consolidated_image(self, image_path: Path) -> tuple[float, int] | None:
        """Analyze a consolidated image to get its usage and size.

        Args:
            image_path: Path to the consolidated image

        Returns:
            Tuple of (usage_percentage, size_bytes) or None if analysis fails
        """
        _LOGGER.debug("Checking consolidated image: %s", image_path.name)

        usage = calculate_image_usage(image_path, self.image_references, self.mount_point)

        try:
            size = image_path.stat().st_size
        except OSError:
            return None

        return usage, size

    def _process_image_manifest(self, image_path: Path, size: int, filter_: list[str]) -> list[ConsolidationCandidate]:
        """Process manifest for a consolidated image and extract candidates.

        Args:
            image_path: Path to the consolidated image
            size: Size of the image in bytes
            filter_: Optional filter for selecting items

        Returns:
            List of candidates from this image, or empty list if processing fails
        """
        manifest = read_manifest_from_alongside(image_path)
        if not manifest or "contents" not in manifest:
            _LOGGER.warning("Cannot reconsolidate %s: no manifest", image_path.name)
            return []

        return extract_candidates_from_manifest(manifest, image_path, self, filter_, size, self.mount_point)

    def gather_reconsolidation_candidates(
        self,
        efficiency_threshold: float,
        max_size_bytes: int,
        undersized_ratio: float,
        filter_: list[str],
    ) -> list[ConsolidationCandidate]:
        """Gather candidates from existing consolidated images for reconsolidation.

        This method analyzes all consolidated images and identifies items that should
        be repacked based on efficiency and size criteria.

        Args:
            efficiency_threshold: Minimum efficiency to keep consolidated image (0.0-1.0)
            max_size_bytes: Maximum size for consolidated images in bytes
            undersized_ratio: Ratio to determine undersized images
            filter_: Optional filter for selecting items

        Returns:
            List of candidate items from consolidated images that should be repacked
        """
        candidates = []

        for _filename_stem, image_path in self.all_cefs_images.items():
            if not is_consolidated_image(image_path):
                continue

            analysis = self._analyze_consolidated_image(image_path)
            if not analysis:
                continue
            usage, size = analysis

            _LOGGER.debug(
                "Image %s: usage=%.1f%%, size=%s (undersized threshold=%s)",
                image_path.name,
                usage,
                humanfriendly.format_size(size, binary=True),
                humanfriendly.format_size(max_size_bytes * undersized_ratio, binary=True),
            )

            should_reconsolidate, reason = should_reconsolidate_image(
                usage=usage,
                size=size,
                efficiency_threshold=efficiency_threshold,
                max_size_bytes=max_size_bytes,
                undersized_ratio=undersized_ratio,
            )

            if not should_reconsolidate:
                _LOGGER.debug("Image %s not marked for reconsolidation", image_path.name)
                continue

            _LOGGER.info("Consolidated image %s marked for reconsolidation: %s", image_path.name, reason)

            image_candidates = self._process_image_manifest(image_path, size, filter_)
            candidates.extend(image_candidates)

        return candidates


def get_extraction_path_from_symlink(symlink_target: Path, mount_point: Path) -> Path:
    """Determine what to extract from a CEFS image based on symlink target.

    Returns the relative path after {mount_point}/XX/HASH/ or Path(".") if at root.

    Args:
        symlink_target: The symlink target path
        mount_point: CEFS mount point (e.g., /cefs)

    Examples (assuming mount_point=/cefs):
        /cefs/ab/abcd1234567890abcdef12/content → Path("content")
        /cefs/ab/abcd1234567890abcdef12 → Path(".")
        /cefs/ab/abcd1234567890abcdef12/gcc-4.5 → Path("gcc-4.5")
        /cefs/ab/abcd1234567890abcdef12/libs/boost → Path("libs/boost")
    """
    parts = symlink_target.parts
    mount_parts = mount_point.parts
    # Need at least mount_point + XX + HASH to have any relative path
    if len(parts) <= len(mount_parts) + 2:
        return Path(".")

    relative_parts = parts[len(mount_parts) + 2 :]
    return Path(*relative_parts)


@dataclass(frozen=True)
class ImageAgeFilterResult:
    """Result of filtering images by age."""

    old_enough: list[Path]
    too_recent: list[tuple[Path, datetime.timedelta]]


@dataclass(frozen=True)
class ImageDeletionResult:
    """Result of deleting a CEFS image with its manifest."""

    success: bool
    deleted_size: int
    errors: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class GCSummary:
    """Summary statistics for garbage collection."""

    total_images: int
    referenced_images: int
    unreferenced_images: int
    space_to_reclaim: int


def filter_images_by_age(
    images: list[Path], min_age_delta: datetime.timedelta, now: datetime.datetime
) -> ImageAgeFilterResult:
    """Filter images by age, separating old enough from too recent.

    Args:
        images: List of image paths to filter
        min_age_delta: Minimum age for deletion
        now: Current time to use for age calculation

    Returns:
        ImageAgeFilterResult with old_enough and too_recent lists
    """
    old_enough = []
    too_recent = []

    for image_path in images:
        try:
            mtime = datetime.datetime.fromtimestamp(image_path.stat().st_mtime)
            age = now - mtime
            if age >= min_age_delta:
                old_enough.append(image_path)
            else:
                too_recent.append((image_path, age))
        except OSError:
            # If we can't stat it, include it as potentially broken
            old_enough.append(image_path)

    return ImageAgeFilterResult(old_enough=old_enough, too_recent=too_recent)


def get_image_description_from_manifest(image_path: Path) -> list[str] | None:
    """Extract content names from an image's manifest file.

    Args:
        image_path: Path to the CEFS image

    Returns:
        List of content names or None if manifest unavailable/invalid
    """
    try:
        manifest = read_manifest_from_alongside(image_path)
        if manifest and "contents" in manifest:
            names = []
            for content in manifest["contents"]:
                if "name" in content:
                    names.append(content["name"])
            return names if names else None
        return None
    except (OSError, yaml.YAMLError):
        return None


def get_image_description(image_path: Path, cefs_mount_point: Path) -> list[str] | None:
    """Get description of image contents from manifest or by mounting.

    First tries to read from manifest, then falls back to mounting the image.

    Args:
        image_path: Path to the CEFS image
        cefs_mount_point: Base mount point for CEFS

    Returns:
        List of content names or None if unable to determine
    """
    # Try manifest first
    names = get_image_description_from_manifest(image_path)
    if names:
        return names

    # Fallback to mounting
    filename_stem = image_path.stem
    # Extract just the hash part for describe_cefs_image
    hash_part = filename_stem.split("_")[0] if "_" in filename_stem else filename_stem
    try:
        contents = describe_cefs_image(hash_part, cefs_mount_point)
        return contents if contents else None
    except OSError:
        return None


def format_image_contents_string(names: list[str] | None, max_items: int) -> str:
    """Format a list of content names for display.

    Args:
        names: List of content names or None
        max_items: Maximum number of items to show before truncating

    Returns:
        Formatted string like "[contains: name1, name2, ...]" or empty string
    """
    if not names:
        return ""

    if len(names) <= max_items:
        return f" [contains: {', '.join(names)}]"
    else:
        shown = names[:max_items]
        return f" [contains: {', '.join(shown)}...]"


def delete_image_with_manifest(image_path: Path) -> ImageDeletionResult:
    """Delete a CEFS image and its associated manifest file.

    Args:
        image_path: Path to the CEFS image to delete

    Returns:
        ImageDeletionResult with success status, size, and any errors
    """
    errors = []
    deleted_size = 0

    # Get size before deletion
    try:
        deleted_size = image_path.stat().st_size
    except OSError as e:
        errors.append(f"Could not stat {image_path}: {e}")
        # Try to delete anyway

    # Delete the image
    try:
        image_path.unlink()
    except OSError as e:
        errors.append(f"Failed to delete {image_path}: {e}")
        return ImageDeletionResult(success=False, deleted_size=0, errors=errors)

    # Delete the manifest if it exists
    manifest_path = image_path.with_suffix(".yaml")
    if manifest_path.exists():
        try:
            manifest_path.unlink()
        except OSError as e:
            errors.append(f"Failed to delete manifest {manifest_path}: {e}")
            # This is non-fatal - image was deleted

    return ImageDeletionResult(success=True, deleted_size=deleted_size, errors=errors)


def is_consolidated_image(image_path: Path) -> bool:
    """Check if a CEFS image is a consolidated image.

    Consolidated images have 'consolidated' in their filename or contain
    multiple subdirectories when mounted.

    Args:
        image_path: Path to the CEFS image

    Returns:
        True if this is a consolidated image, False otherwise
    """
    # Check filename pattern first (fast)
    if "_consolidated" in image_path.name:
        return True

    # Check manifest for multiple contents (also fast)
    try:
        manifest = read_manifest_from_alongside(image_path)
        if manifest and "contents" in manifest:
            return len(manifest["contents"]) > 1
    except (OSError, yaml.YAMLError):
        pass

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

    # Helper function to check if destination is referenced
    def is_destination_referenced(dest_path: Path) -> bool:
        full_path = Path(dest_path)
        main_ref = check_if_symlink_references_image(full_path, filename_stem, mount_point)
        bak_path = full_path.with_name(full_path.name + ".bak")
        bak_ref = check_if_symlink_references_image(bak_path, filename_stem, mount_point)
        return main_ref or bak_ref

    # For individual images, it's binary
    if len(expected_destinations) == 1:
        return 100.0 if is_destination_referenced(expected_destinations[0]) else 0.0

    # For consolidated images, check each subdirectory
    referenced_count = sum(1 for dest in expected_destinations if is_destination_referenced(dest))
    return (referenced_count / len(expected_destinations)) * 100.0


def check_if_symlink_references_image(symlink_path: Path, image_stem: str, mount_point: Path) -> bool:
    if not symlink_path.is_symlink():
        return False

    try:
        target = symlink_path.readlink()
        if target.is_absolute() and target.is_relative_to(mount_point):
            mount_parts_len = len(mount_point.parts)
            parts = target.parts
            if len(parts) >= mount_parts_len + 2:
                # The directory name is at index mount_parts_len + 1
                # e.g., for /cefs/0d/0d163f7f3ee984e50fd7d14f_consolidated/subdir
                # parts[mount_parts_len + 1] is "0d163f7f3ee984e50fd7d14f_consolidated"
                target_dir = parts[mount_parts_len + 1]
                return target_dir == image_stem
    except (OSError, IndexError):
        pass

    return False


@dataclass
class ImageUsageStats:
    """Statistics about CEFS image usage."""

    total_images: int
    individual_images: int
    consolidated_images: int
    fully_used_consolidated: int
    partially_used_consolidated: list[tuple[Path, float]]  # (path, usage_percentage)
    unused_images: list[Path]
    total_space: int
    wasted_space_estimate: int


def get_current_symlink_targets(path: Path) -> list[Path]:
    """Get symlink targets for a path and its .bak backup if they exist.

    During CEFS operations, directories are moved to .bak before creating symlinks.
    Both the main path and backup could reference CEFS images, especially after
    re-conversions or with deferred cleanup.

    Args:
        path: The path to check

    Returns:
        List of symlink targets (empty if no symlinks exist)
    """
    targets = []
    for p in [path, path.with_name(path.name + ".bak")]:
        if p.is_symlink():
            try:
                targets.append(p.readlink())
            except OSError:
                pass
    return targets


def get_consolidated_image_usage_stats(
    state: CEFSState,
) -> ImageUsageStats:
    """Calculate detailed usage statistics for CEFS images.

    Args:
        state: CEFSState object with image information

    Returns:
        ImageUsageStats with detailed breakdown
    """
    individual_images = 0
    consolidated_images = 0
    fully_used_consolidated = 0
    partially_used_consolidated = []
    unused_images = []
    total_space = 0
    wasted_space_estimate = 0

    for _filename_stem, image_path in state.all_cefs_images.items():
        try:
            size = image_path.stat().st_size
            total_space += size
        except OSError:
            size = 0

        usage = calculate_image_usage(image_path, state.image_references, state.mount_point)

        if is_consolidated_image(image_path):
            consolidated_images += 1
            if usage == 100.0:
                fully_used_consolidated += 1
            elif usage > 0:
                partially_used_consolidated.append((image_path, usage))
                # Estimate wasted space as the unused portion
                wasted_space_estimate += int(size * (100 - usage) / 100)
            else:
                unused_images.append(image_path)
                wasted_space_estimate += size
        else:
            individual_images += 1
            if usage == 0:
                unused_images.append(image_path)
                wasted_space_estimate += size

    # Sort partially used by usage percentage
    partially_used_consolidated.sort(key=lambda x: x[1])

    return ImageUsageStats(
        total_images=len(state.all_cefs_images),
        individual_images=individual_images,
        consolidated_images=consolidated_images,
        fully_used_consolidated=fully_used_consolidated,
        partially_used_consolidated=partially_used_consolidated,
        unused_images=unused_images,
        total_space=total_space,
        wasted_space_estimate=wasted_space_estimate,
    )


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
    else:
        mount_str = str(mount_point) + "/"
        if current_target and str(current_target).startswith(mount_str):
            replacement_info = str(current_target).replace(mount_str, "")
            return f"          ✗ {content['name']} → replaced by {replacement_info}"
        else:
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
    elif usage / 100.0 < efficiency_threshold:
        return True, f"low efficiency ({usage:.1f}%)"
    elif size < max_size_bytes * undersized_ratio:
        return True, f"undersized ({humanfriendly.format_size(size, binary=True)})"
    return False, ""


def find_small_consolidated_images(state: CEFSState, size_threshold: int) -> list[Path]:
    """Find consolidated images that are candidates for reconsolidation.

    Args:
        state: CEFS state object with image information
        size_threshold: Size threshold in bytes

    Returns:
        List of paths to small consolidated images
    """
    small_images = []
    for _filename_stem, image_path in state.all_cefs_images.items():
        if not is_consolidated_image(image_path):
            continue
        try:
            size = image_path.stat().st_size
            if size < size_threshold:
                small_images.append(image_path)
        except OSError:
            continue
    return small_images


def should_include_manifest_item(
    content: dict, image_path: Path, mount_point: Path, filter_: list[str]
) -> tuple[bool, list[Path]]:
    """Check if a manifest item should be included for reconsolidation.

    Args:
        content: Manifest entry to check
        image_path: Path to the consolidated image
        mount_point: CEFS mount point
        filter_: Optional filter for selecting items

    Returns:
        Tuple of (should_include, targets) where targets are the current symlink targets
    """
    if "destination" not in content or "name" not in content:
        raise ValueError(f"Malformed manifest entry missing required fields: {content}")

    dest_path = Path(content["destination"])
    targets = get_current_symlink_targets(dest_path)

    # Check if this item is still referenced to this image
    if not any(is_item_still_using_image(target, image_path, mount_point) for target in targets):
        return False, targets

    # Apply filter if provided
    if filter_ and not any(f in content["name"] for f in filter_):
        return False, targets

    return True, targets


def determine_extraction_path(targets: list[Path], image_path: Path, mount_point: Path) -> Path:
    """Determine the extraction path from symlink targets.

    Args:
        targets: List of symlink targets
        image_path: Path to the consolidated image
        mount_point: CEFS mount point

    Returns:
        Path within the consolidated image to extract from
    """
    for target in targets:
        if is_item_still_using_image(target, image_path, mount_point):
            if len(target.parts) > 4:
                return Path(*target.parts[4:])
            break
    return Path(".")


def create_candidate_from_entry(
    content: dict,
    dest_path: Path,
    image_path: Path,
    extraction_path: Path,
    state: CEFSState,
    item_size: int,
) -> ConsolidationCandidate:
    """Create a ConsolidationCandidate from a manifest entry.

    Args:
        content: Manifest entry
        dest_path: Destination path from manifest
        image_path: Path to the consolidated image
        extraction_path: Path within the image to extract
        state: CEFS state object
        item_size: Estimated size per item

    Returns:
        ConsolidationCandidate object
    """
    # Fix redundant Path construction - dest_path is already a Path
    nfs_path = dest_path if dest_path.is_absolute() else state.nfs_dir / dest_path

    return ConsolidationCandidate(
        name=content["name"],
        nfs_path=nfs_path,
        squashfs_path=image_path,
        extraction_path=extraction_path,
        size=item_size,
        from_reconsolidation=True,
    )


def extract_candidates_from_manifest(
    manifest: dict,
    image_path: Path,
    state: CEFSState,
    filter_: list[str],
    size: int,
    mount_point: Path,
) -> list[ConsolidationCandidate]:
    """Extract reconsolidation candidates from a consolidated image manifest.

    Args:
        manifest: Image manifest dictionary
        image_path: Path to the consolidated image
        state: CEFS state object
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

    candidates = []
    contents = manifest.get("contents", [])
    item_size = size // len(contents) if contents else 0  # Estimate size per item

    for content in contents:
        should_include, targets = should_include_manifest_item(content, image_path, mount_point, filter_)
        if not should_include:
            continue

        dest_path = Path(content["destination"])
        extraction_path = determine_extraction_path(targets, image_path, mount_point)
        candidate = create_candidate_from_entry(content, dest_path, image_path, extraction_path, state, item_size)
        candidates.append(candidate)

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
) -> tuple[list[tuple[Path, Path, str, Path]], dict[Path, str]]:
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

        # Post-consolidation safety check even for existing images
        # Skip this check in dry-run mode
        if not dry_run and updated > 0:
            _LOGGER.info("Running post-consolidation safety checks for group %d", group_idx + 1)
            failed_items = []

            for item in group:
                try:
                    # Find the installable by exact name
                    installable = find_installable_func(item.name)

                    # Check if it reports as installed using the canonical check
                    if not installable.is_installed():
                        failed_items.append((item.name, item.nfs_path))
                        _LOGGER.error("Post-consolidation check failed: %s reports not installed", item.name)
                except ValueError as e:
                    # This is a hard error - we can't find the installable or found multiple
                    _LOGGER.error("Failed to find installable for validation: %s", e)
                    failed_items.append((item.name, item.nfs_path))

            # Rollback failed items individually
            if failed_items:
                _LOGGER.warning("Found %d items failing is_installed() check, attempting rollback", len(failed_items))
                rollback_count = 0
                for name, symlink_path in failed_items:
                    # Try to restore from backup
                    backup_path = Path(str(symlink_path) + ".bak")
                    if backup_path.exists():
                        try:
                            # Remove the broken symlink
                            if symlink_path.exists() or symlink_path.is_symlink():
                                symlink_path.unlink()
                            # Restore the backup
                            backup_path.rename(symlink_path)
                            _LOGGER.info("Rolled back symlink for %s from backup", name)
                            rollback_count += 1
                            updated -= 1  # Decrement the updated count
                        except OSError as e:
                            _LOGGER.error("Failed to rollback symlink for %s: %s", name, e)
                    else:
                        _LOGGER.warning("No backup found for %s, cannot rollback", name)

                if rollback_count < len(failed_items):
                    _LOGGER.error(
                        "Failed to rollback %d items for group %d", len(failed_items) - rollback_count, group_idx + 1
                    )

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

        # Post-consolidation safety check: verify all installables report as installed
        # Skip this check in dry-run mode
        if not dry_run:
            _LOGGER.info("Running post-consolidation safety checks for group %d", group_idx + 1)
            failed_items = []

            for item in group:
                try:
                    # Find the installable by exact name
                    installable = find_installable_func(item.name)

                    # Check if it reports as installed using the canonical check
                    if not installable.is_installed():
                        failed_items.append((item.name, item.nfs_path))
                        _LOGGER.error("Post-consolidation check failed: %s reports not installed", item.name)
                except ValueError as e:
                    # This is a hard error - we can't find the installable or found multiple
                    _LOGGER.error("Failed to find installable for validation: %s", e)
                    failed_items.append((item.name, item.nfs_path))

            # Rollback failed items individually
            if failed_items:
                _LOGGER.warning("Found %d items failing is_installed() check, attempting rollback", len(failed_items))
                rollback_count = 0
                for name, symlink_path in failed_items:
                    # Try to restore from backup
                    backup_path = Path(str(symlink_path) + ".bak")
                    if backup_path.exists():
                        try:
                            # Remove the broken symlink
                            if symlink_path.exists() or symlink_path.is_symlink():
                                symlink_path.unlink()
                            # Restore the backup
                            backup_path.rename(symlink_path)
                            _LOGGER.info("Rolled back symlink for %s from backup", name)
                            rollback_count += 1
                            updated -= 1  # Decrement the updated count
                        except OSError as e:
                            _LOGGER.error("Failed to rollback symlink for %s: %s", name, e)
                    else:
                        _LOGGER.warning("No backup found for %s, cannot rollback", name)

                if rollback_count < len(failed_items):
                    _LOGGER.error(
                        "Failed to rollback %d items for group %d", len(failed_items) - rollback_count, group_idx + 1
                    )
                    # Don't fail the entire consolidation, but log the issue prominently

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


# ============================================================================
# CEFS Operations Functions
# ============================================================================


def convert_to_cefs(
    installable,
    destination_path: Path,
    squashfs_image_path: Path,
    config_squashfs,
    config_cefs,
    force: bool,
    defer_cleanup: bool,
    dry_run: bool,
) -> bool:
    """Convert a single installable from squashfs to CEFS.

    Args:
        installable: The installable object to convert
        destination_path: NFS destination path
        squashfs_image_path: Path to the squashfs image
        config_squashfs: Squashfs configuration
        config_cefs: CEFS configuration
        force: Force conversion even if already converted
        defer_cleanup: Defer cleanup of backup directories
        dry_run: Whether this is a dry run

    Returns:
        True if conversion was successful or already converted.
    """
    nfs_path = destination_path / installable.install_path

    if not squashfs_image_path.exists():
        _LOGGER.error("No squashfs image found for %s at %s", installable.name, squashfs_image_path)
        return False

    match detect_nfs_state(nfs_path):
        case "symlink":
            if not force:
                _LOGGER.info("Already converted to CEFS: %s", installable.name)
                return True
        case "missing":
            _LOGGER.error("NFS directory missing for %s: %s", installable.name, nfs_path)
            return False

    # Generate CEFS filename and paths
    try:
        _LOGGER.info("Calculating hash for %s...", squashfs_image_path)
        relative_path = squashfs_image_path.relative_to(config_squashfs.image_dir)
        filename = get_cefs_filename_for_image(squashfs_image_path, "convert", relative_path)
        _LOGGER.info("Filename: %s", filename)
    except OSError as e:
        _LOGGER.error("Failed to calculate hash for %s: %s", installable.name, e)
        return False

    cefs_paths = get_cefs_paths(config_cefs.image_dir, config_cefs.mount_point, filename)

    installable_info = create_installable_manifest_entry(installable.name, nfs_path)
    manifest = create_manifest(
        operation="convert",
        description=f"Created through conversion of {installable.name}",
        contents=[installable_info],
    )

    # Copy squashfs to CEFS images directory if not already there
    # Never overwrite - hash ensures content is identical
    if cefs_paths.image_path.exists():
        _LOGGER.info("CEFS image already exists: %s", cefs_paths.image_path)
        # Still need to create symlink even if image exists
        try:
            backup_and_symlink(nfs_path, cefs_paths.mount_path, dry_run, defer_cleanup)
        except RuntimeError as e:
            _LOGGER.error("Failed to create symlink for %s: %s", installable.name, e)
            return False
    else:
        # Deploy image and create symlink within transaction
        try:
            with deploy_to_cefs_transactional(squashfs_image_path, cefs_paths.image_path, manifest, dry_run):
                # Create symlink while transaction is active
                backup_and_symlink(nfs_path, cefs_paths.mount_path, dry_run, defer_cleanup)
                # Manifest will be automatically finalized on successful exit
        except RuntimeError as e:
            _LOGGER.error("Failed to convert %s to CEFS: %s", installable.name, e)
            return False

    # Post-migration validation (skip in dry-run)
    if not dry_run:
        if not nfs_path.is_symlink():
            _LOGGER.error("Post-migration check failed: %s is not a symlink", nfs_path)
            return False

        if not installable.is_installed():
            _LOGGER.error("Post-migration check: %s reports not installed", installable.name)
            return False
        _LOGGER.info("Post-migration check: %s still installed", installable.name)

    _LOGGER.info("Successfully converted %s to CEFS", installable.name)
    return True


def format_verbose_image_details(
    image_path: Path,
    usage: float,
    items_info: list[str] | None,
    manifest: dict | None,
    mount_point: Path,
) -> list[str]:
    """Format verbose details for a partially used consolidated image.

    Args:
        image_path: Path to the image
        usage: Usage percentage
        items_info: List of item descriptions
        manifest: Manifest dictionary
        mount_point: CEFS mount point

    Returns:
        List of formatted lines
    """
    lines = []

    if not items_info:
        lines.append(f"        {image_path.name} ({usage:.1f}%)")
        return lines

    total_items = len(items_info)
    used_items = int(total_items * usage / 100)
    lines.append(f"        {image_path.name} ({usage:.1f}% - {used_items}/{total_items} items)")

    # Show what replaced each item if partially used
    if manifest and "contents" in manifest and usage < 100:
        for content in manifest["contents"]:
            if "destination" in content:
                dest_path = Path(content["destination"])
                targets = get_current_symlink_targets(dest_path)
                # Find which target (if any) points to this image for status reporting
                current_target = next(
                    (t for t in targets if is_item_still_using_image(t, image_path, mount_point)), None
                )
                status = get_consolidated_item_status(content, image_path, current_target, mount_point)
                if status:
                    lines.append(status)

    return lines


def format_usage_statistics(stats, state: CEFSState, verbose: bool, cefs_mount_point: Path) -> list[str]:
    """Format detailed usage statistics.

    Args:
        stats: Usage statistics object
        state: CEFSState object
        verbose: Whether to show verbose output
        cefs_mount_point: CEFS mount point

    Returns:
        List of formatted output lines
    """
    lines = []
    lines.append("\nImage Statistics:")
    lines.append(f"  Total images: {stats.total_images}")
    lines.append(f"  Individual images: {stats.individual_images}")
    lines.append(f"  Consolidated images: {stats.consolidated_images}")

    if stats.consolidated_images > 0:
        lines.append(f"    - Fully used (100%): {stats.fully_used_consolidated}")

        ranges = group_images_by_usage(stats.partially_used_consolidated)

        lines.append(f"    - Partially used: {len(stats.partially_used_consolidated)}")
        for range_name, images in ranges.items():
            if images:
                lines.append(f"      * {range_name} used: {len(images)} images")
                if verbose:
                    for image_path, usage in images:
                        items_info = get_image_description(image_path, cefs_mount_point)
                        manifest = read_manifest_from_alongside(image_path)
                        detail_lines = format_verbose_image_details(
                            image_path, usage, items_info, manifest, cefs_mount_point
                        )
                        lines.extend(detail_lines)

        # Count unused consolidated images
        unused_consolidated = len([p for p in stats.unused_images if is_consolidated_image(p)])
        lines.append(f"    - Unused (0%): {unused_consolidated}")

    lines.append("\nSpace Analysis:")
    lines.append(f"  Total CEFS space: {humanfriendly.format_size(stats.total_space, binary=True)}")
    if stats.wasted_space_estimate > 0:
        lines.append(
            f"  Wasted in partial images: ~{humanfriendly.format_size(stats.wasted_space_estimate, binary=True)} (estimated)"
        )

    small_consolidated = find_small_consolidated_images(state, 5 * 1024 * 1024 * 1024)
    if small_consolidated:
        lines.append(f"  Potential consolidation: {len(small_consolidated)} small consolidated images could be merged")

    if verbose:
        lines.append("\nRun 'ce cefs consolidate --reconsolidate' to optimize partially used images")

    return lines


def gather_reconsolidation_candidates(
    state: CEFSState,
    efficiency_threshold: float,
    max_size_bytes: int,
    undersized_ratio: float,
    filter_: list[str] | None = None,
) -> list[ConsolidationCandidate]:
    """Gather candidates from existing consolidated images for reconsolidation.

    Args:
        state: CEFSState object
        efficiency_threshold: Minimum efficiency to keep consolidated image (0.0-1.0)
        max_size_bytes: Maximum size for consolidated images
        undersized_ratio: Ratio for determining undersized images
        filter_: Optional filter for selecting items

    Returns:
        List of candidate items from consolidated images that should be repacked
    """
    # Use the CEFSState's method to gather candidates
    return state.gather_reconsolidation_candidates(
        efficiency_threshold=efficiency_threshold,
        max_size_bytes=max_size_bytes,
        undersized_ratio=undersized_ratio,
        filter_=filter_ or [],
    )


# ============================================================================
# FSCK Helper Functions
# ============================================================================


@dataclass
class FSCKResults:
    """Results from CEFS filesystem check."""

    total_images: int = 0
    valid_manifests: int = 0
    missing_manifests: list[Path] = field(default_factory=list)
    old_format_manifests: list[Path] = field(default_factory=list)
    invalid_name_manifests: list[tuple[Path, str]] = field(default_factory=list)
    other_invalid_manifests: list[tuple[Path, str]] = field(default_factory=list)
    unreadable_manifests: list[tuple[Path, str]] = field(default_factory=list)
    inprogress_files: list[FileWithAge] = field(default_factory=list)
    pending_backups: list[FileWithAge] = field(default_factory=list)
    pending_deletes: list[FileWithAge] = field(default_factory=list)

    @property
    def total_invalid(self) -> int:
        """Total number of invalid manifests."""
        return (
            len(self.missing_manifests)
            + len(self.old_format_manifests)
            + len(self.invalid_name_manifests)
            + len(self.other_invalid_manifests)
            + len(self.unreadable_manifests)
        )

    @property
    def has_issues(self) -> bool:
        """Check if any issues were found."""
        return (
            self.total_invalid > 0
            or len(self.inprogress_files) > 0
            or len(self.pending_backups) > 0
            or len(self.pending_deletes) > 0
        )


def find_files_by_pattern(
    base_dir: Path,
    pattern: str,
    current_time: float,
    max_depth: int | None = None,
) -> list[FileWithAge]:
    """Find files matching pattern and return with age.

    Args:
        base_dir: Directory to search
        pattern: Glob pattern (e.g., "*.bak")
        current_time: Current time for age calculation
        max_depth: Maximum directory depth (None for unlimited)

    Returns:
        List of FileWithAge tuples
    """
    # Build list of glob patterns based on max_depth
    if max_depth is None:
        patterns = [f"**/{pattern}"]
    else:
        patterns = [
            pattern if depth == 0 else "/".join(["*"] * depth) + "/" + pattern for depth in range(max_depth + 1)
        ]

    # Single loop to process all patterns
    results = []
    for glob_pattern in patterns:
        for path in base_dir.glob(glob_pattern):
            try:
                # Use lstat to get the modification time of the item itself (not following symlinks)
                mtime = path.lstat().st_mtime
                results.append(FileWithAge(path, current_time - mtime))
            except OSError:
                # File disappeared or permission denied - skip silently
                continue

    return results


def check_inprogress_files(cefs_image_dir: Path, current_time: float) -> list[FileWithAge]:
    """Check for yaml.inprogress files only (no sqfs checks).

    Args:
        cefs_image_dir: Path to CEFS images directory
        current_time: Current time for age calculation

    Returns:
        List of FileWithAge tuples sorted by age (oldest first)
    """
    # CEFS dir uses unlimited depth (it's local, not NFS)
    files = find_files_by_pattern(cefs_image_dir, "*.yaml.inprogress", current_time, max_depth=None)
    # Sort by age (oldest first)
    return sorted(files, key=lambda x: x.age_seconds, reverse=True)


def validate_single_manifest(manifest_path: Path, mount_point: Path, filename_stem: str) -> tuple[bool, str | None]:
    """Validate a single manifest file.

    Args:
        manifest_path: Path to the manifest file
        mount_point: CEFS mount point
        filename_stem: Stem of the image filename

    Returns:
        Tuple of (is_valid, error_type)
        where error_type is None if valid, or one of:
        - "missing": manifest file doesn't exist
        - "unreadable": file exists but can't be read
        - "old_format": uses deprecated 'target' field
        - "invalid_name": has invalid installable names
        - "other": other validation errors
    """
    if not manifest_path.exists():
        return False, "missing"

    try:
        with manifest_path.open(encoding="utf-8") as f:
            manifest_dict = yaml.safe_load(f)
    except (OSError, yaml.YAMLError):
        return False, "unreadable"

    contents = manifest_dict.get("contents", []) if manifest_dict else []

    if any("target" in content for content in contents):
        return False, "old_format"

    try:
        validate_manifest(manifest_dict)
    except ValueError as e:
        error_msg = str(e).lower()
        error_type = (
            "invalid_name" if "invalid name" in error_msg or "entries with invalid name" in error_msg else "other"
        )
        return False, error_type

    return True, None


def run_fsck_validation(
    state: CEFSState,
    mount_point: Path,
) -> FSCKResults:
    """Run CEFS filesystem validation checks.

    Args:
        state: CEFSState with scanned images
        mount_point: CEFS mount point

    Returns:
        FSCKResults containing all validation results
    """
    results = FSCKResults()

    for filename_stem, image_path in state.all_cefs_images.items():
        results.total_images += 1
        manifest_path = image_path.with_suffix(".yaml")
        is_valid, error_type = validate_single_manifest(manifest_path, mount_point, filename_stem)

        if is_valid:
            results.valid_manifests += 1
        else:
            match error_type:
                case "missing":
                    results.missing_manifests.append(manifest_path)
                case "old_format":
                    results.old_format_manifests.append(manifest_path)
                case "invalid_name" | "other":
                    # Re-validate to capture the specific error message since we only got the type earlier
                    try:
                        with manifest_path.open(encoding="utf-8") as f:
                            manifest_dict = yaml.safe_load(f)
                        validate_manifest(manifest_dict)
                    except ValueError as e:
                        if error_type == "invalid_name":
                            results.invalid_name_manifests.append((manifest_path, str(e)))
                        else:
                            results.other_invalid_manifests.append((manifest_path, str(e)))
                case "unreadable":
                    results.unreadable_manifests.append((manifest_path, "Cannot read manifest file"))

    current_time = time.time()
    results.inprogress_files = check_inprogress_files(state.cefs_image_dir, current_time)
    results.pending_backups = find_files_by_pattern(
        state.nfs_dir, "*.bak", current_time, max_depth=NFS_MAX_RECURSION_DEPTH
    )
    results.pending_deletes = find_files_by_pattern(
        state.nfs_dir, "*.DELETE_ME_*", current_time, max_depth=NFS_MAX_RECURSION_DEPTH
    )

    return results
