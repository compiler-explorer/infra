#!/usr/bin/env python3
"""CEFS (Compiler Explorer FileSystem) v2 commands."""

from __future__ import annotations

import datetime
import logging
import os
import shutil
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path

import click
import humanfriendly

from lib.ce_install import CliContext, cli
from lib.cefs import (
    CEFSState,
    backup_and_symlink,
    calculate_image_usage,
    check_temp_space_available,
    create_consolidated_image,
    delete_image_with_manifest,
    deploy_to_cefs_with_manifest,
    detect_nfs_state,
    filter_images_by_age,
    format_image_contents_string,
    get_cefs_filename_for_image,
    get_cefs_paths,
    get_current_symlink_target,
    get_extraction_path_from_symlink,
    get_image_description,
    is_consolidated_image,
    parse_cefs_target,
    snapshot_symlink_targets,
    update_symlinks_for_consolidation,
    validate_cefs_mount_point,
    verify_symlinks_unchanged,
)
from lib.cefs_manifest import (
    create_installable_manifest_entry,
    create_manifest,
    finalize_manifest,
    read_manifest_from_alongside,
    sanitize_path_for_filename,
)
from lib.installable.installable import Installable

_LOGGER = logging.getLogger(__name__)


def convert_to_cefs(context: CliContext, installable: Installable, force: bool, defer_cleanup: bool) -> bool:
    """Convert a single installable from squashfs to CEFS.

    Returns True if conversion was successful or already converted.
    """
    squashfs_image_path = context.config.squashfs.image_dir / f"{installable.install_path}.img"
    nfs_path = context.installation_context.destination / installable.install_path

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
        relative_path = squashfs_image_path.relative_to(context.config.squashfs.image_dir)
        filename = get_cefs_filename_for_image(squashfs_image_path, "convert", relative_path)
        _LOGGER.info("Filename: %s", filename)
    except OSError as e:
        _LOGGER.error("Failed to calculate hash for %s: %s", installable.name, e)
        return False

    cefs_paths = get_cefs_paths(context.config.cefs.image_dir, context.config.cefs.mount_point, filename)

    installable_info = create_installable_manifest_entry(installable.name, nfs_path)
    manifest = create_manifest(
        operation="convert",
        description=f"Created through conversion of {installable.name}",
        contents=[installable_info],
    )

    # Copy squashfs to CEFS images directory if not already there
    # Never overwrite - hash ensures content is identical
    if image_already_existed := cefs_paths.image_path.exists():
        _LOGGER.info("CEFS image already exists: %s", cefs_paths.image_path)
    elif context.installation_context.dry_run:
        _LOGGER.info("Would copy %s to %s", squashfs_image_path, cefs_paths.image_path)
        _LOGGER.info("Would write manifest alongside image")
    else:
        try:
            deploy_to_cefs_with_manifest(squashfs_image_path, cefs_paths.image_path, manifest)
        except RuntimeError as e:
            _LOGGER.error("Failed to deploy image for %s: %s", installable.name, e)
            return False

    # Backup NFS directory and create symlink
    try:
        backup_and_symlink(nfs_path, cefs_paths.mount_path, context.installation_context.dry_run, defer_cleanup)
    except RuntimeError as e:
        _LOGGER.error("Failed to create symlink for %s: %s", installable.name, e)
        return False

    # Finalize the manifest now that symlink is created (critical for GC safety), but only if we just created the image.
    if not context.installation_context.dry_run and not image_already_existed:
        try:
            finalize_manifest(cefs_paths.image_path)
            _LOGGER.debug("Finalized manifest for %s", installable.name)
        except RuntimeError as e:
            _LOGGER.error("Failed to finalize manifest for %s: %s", installable.name, e)
            return False

    # Post-migration validation (skip in dry-run)
    if not context.installation_context.dry_run:
        if not nfs_path.is_symlink():
            _LOGGER.error("Post-migration check failed: %s is not a symlink", nfs_path)
            return False

        if not installable.is_installed():
            _LOGGER.error("Post-migration check: %s reports not installed", installable.name)
            return False
        _LOGGER.info("Post-migration check: %s still installed", installable.name)

    _LOGGER.info("Successfully converted %s to CEFS", installable.name)
    return True


@cli.group()
def cefs():
    """CEFS (Compiler Explorer FileSystem) v2 commands."""


def _print_basic_config(context: CliContext) -> None:
    """Print basic CEFS and Squashfs configuration."""
    print("CEFS Configuration:")
    print(f"  Enabled: {context.config.cefs.enabled}")
    print(f"  Mount Point: {context.config.cefs.mount_point}")
    print(f"  Image Directory: {context.config.cefs.image_dir}")
    print(f"  Local Temp Directory: {context.config.cefs.local_temp_dir}")
    print("Squashfs Configuration:")
    print(f"  Traditional Enabled: {context.config.squashfs.traditional_enabled}")
    print(f"  Compression: {context.config.squashfs.compression}")
    print(f"  Compression Level: {context.config.squashfs.compression_level}")


def _group_images_by_usage(partially_used: list[tuple[Path, float]]) -> dict[str, list[tuple[Path, float]]]:
    """Group partially used images by usage percentage ranges."""
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


def _is_item_still_using_image(current_target: Path | None, image_path: Path) -> bool:
    """Check if a consolidated item is still using its original image."""
    if not current_target or not str(current_target).startswith("/cefs/"):
        return False

    # Get the filename stem from the symlink target
    # Format: /cefs/XX/FILENAME_STEM/... where FILENAME_STEM is like "abc123_consolidated"
    parts = current_target.parts
    if len(parts) < 4:
        return False

    target_filename_stem = parts[3]
    image_filename_stem = image_path.stem

    return target_filename_stem == image_filename_stem


def _get_consolidated_item_status(content: dict, image_path: Path, current_target: Path | None) -> str:
    """Get the status string for a single item in a consolidated image."""
    if "name" not in content:
        return ""

    if _is_item_still_using_image(current_target, image_path):
        return f"          ✓ {content['name']}"
    else:
        if current_target and str(current_target).startswith("/cefs/"):
            replacement_info = str(current_target).replace("/cefs/", "")
            return f"          ✗ {content['name']} → replaced by {replacement_info}"
        else:
            return f"          ✗ {content['name']} → not in CEFS"


def _format_verbose_image_details(
    image_path: Path, usage: float, items_info: list[str] | None, manifest: dict | None, nfs_dir: Path
) -> list[str]:
    """Format verbose details for a partially used consolidated image."""
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
                current_target = get_current_symlink_target(dest_path, nfs_dir)
                status = _get_consolidated_item_status(content, image_path, current_target)
                if status:
                    lines.append(status)

    return lines


def _format_usage_statistics(
    stats, state: CEFSState, verbose: bool, nfs_dir: Path, cefs_mount_point: Path
) -> list[str]:
    """Format detailed usage statistics."""
    lines = []
    lines.append("\nImage Statistics:")
    lines.append(f"  Total images: {stats.total_images}")
    lines.append(f"  Individual images: {stats.individual_images}")
    lines.append(f"  Consolidated images: {stats.consolidated_images}")

    if stats.consolidated_images > 0:
        lines.append(f"    - Fully used (100%): {stats.fully_used_consolidated}")

        ranges = _group_images_by_usage(stats.partially_used_consolidated)

        lines.append(f"    - Partially used: {len(stats.partially_used_consolidated)}")
        for range_name, images in ranges.items():
            if images:
                lines.append(f"      * {range_name} used: {len(images)} images")
                if verbose:
                    for image_path, usage in images:
                        items_info = get_image_description(image_path, cefs_mount_point)
                        manifest = read_manifest_from_alongside(image_path)
                        detail_lines = _format_verbose_image_details(image_path, usage, items_info, manifest, nfs_dir)
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

    small_consolidated = _find_small_consolidated_images(state, 5 * 1024 * 1024 * 1024)
    if small_consolidated:
        lines.append(f"  Potential consolidation: {len(small_consolidated)} small consolidated images could be merged")

    if verbose:
        lines.append("\nRun 'ce cefs consolidate --include-reconsolidation' to optimize partially used images")

    return lines


def _find_small_consolidated_images(state: CEFSState, size_threshold: int) -> list[Path]:
    """Find consolidated images smaller than the threshold."""
    small_consolidated = []
    for image_path in state.all_cefs_images.values():
        if is_consolidated_image(image_path):
            try:
                size = image_path.stat().st_size
                if size < size_threshold:
                    small_consolidated.append(image_path)
            except OSError:
                pass
    return small_consolidated


@cefs.command()
@click.pass_obj
@click.option("--show-usage", is_flag=True, help="Show detailed usage statistics for CEFS images")
@click.option("--verbose", is_flag=True, help="Show per-image details when using --show-usage")
def status(context, show_usage: bool, verbose: bool):
    """Show CEFS configuration status."""
    _print_basic_config(context)

    if not show_usage:
        return

    print("\nCEFS Image Usage Statistics:")
    print("  Scanning images and checking references...")

    state = CEFSState(
        nfs_dir=context.installation_context.destination,
        cefs_image_dir=context.config.cefs.image_dir,
    )

    state.scan_cefs_images_with_manifests()
    state.check_symlink_references()

    stats = state.get_usage_stats()
    output_lines = _format_usage_statistics(
        stats, state, verbose, context.installation_context.destination, context.config.cefs.mount_point
    )
    for line in output_lines:
        print(line)


@cefs.command()
@click.pass_obj
@click.option("--force", is_flag=True, help="Force conversion even if already converted to CEFS")
@click.option(
    "--defer-backup-cleanup",
    is_flag=True,
    help="Rename old .bak directories to .DELETE_ME_<timestamp> instead of deleting them immediately",
)
@click.argument("filter_", metavar="FILTER", nargs=-1)
def convert(context: CliContext, filter_: list[str], force: bool, defer_backup_cleanup: bool):
    """Convert squashfs images to CEFS format for targets matching FILTER."""
    if not validate_cefs_mount_point(context.config.cefs.mount_point):
        _LOGGER.error("CEFS mount point validation failed. Run 'ce cefs setup' first.")
        raise click.ClickException("CEFS not properly configured")

    installables = context.get_installables(filter_)

    if not installables:
        _LOGGER.warning("No installables match filter: %s", " ".join(filter_))
        return

    successful = 0
    failed = 0
    skipped = 0

    for installable in installables:
        if not installable.is_squashable:
            _LOGGER.debug("Skipping non-squashable: %s", installable.name)
            skipped += 1
            continue

        _LOGGER.info("Converting %s...", installable.name)
        if convert_to_cefs(context, installable, force, defer_backup_cleanup):
            successful += 1
        else:
            failed += 1

    _LOGGER.info("Conversion complete: %d successful, %d failed, %d skipped", successful, failed, skipped)

    if failed > 0:
        raise click.ClickException(f"Failed to convert {failed} installables")


@cefs.command()
@click.pass_obj
@click.option("--dry-run", is_flag=True, help="Show what would be done without making changes")
def setup(context: CliContext, dry_run: bool):
    """Set up CEFS autofs configuration for local testing.

    This replicates the production setup_cefs() function from setup-common.sh.
    Requires sudo privileges for system configuration changes.
    """
    cefs_mount_point = context.config.cefs.mount_point
    cefs_image_dir = context.config.cefs.image_dir

    def run_cmd(cmd, description):
        """Run command or show what would be run in dry-run mode."""
        if dry_run:
            _LOGGER.info("Would run: %s", " ".join(cmd))
        else:
            _LOGGER.info("%s", description)
            subprocess.check_call(cmd)

    _LOGGER.info("Setting up CEFS autofs configuration")
    _LOGGER.info("Mount point: %s", cefs_mount_point)
    _LOGGER.info("Image directory: %s", cefs_image_dir)

    if dry_run:
        _LOGGER.info("DRY RUN mode - showing commands that would be executed:")

    # IMPORTANT: any changes to this setup should be reflected in the setup_cefs
    # bash script in setup-common.sh (and vice versa).
    try:
        # Step 1: Create CEFS mount point
        run_cmd(["sudo", "mkdir", "-p", cefs_mount_point], f"Creating CEFS mount point: {cefs_mount_point}")

        # Step 2: Create first-level autofs map file (handles /cefs/XX -> nested autofs)
        auto_cefs_content = "* -fstype=autofs program:/etc/auto.cefs.sub"
        run_cmd(["sudo", "bash", "-c", f"echo '{auto_cefs_content}' > /etc/auto.cefs"], "Creating /etc/auto.cefs")

        # Step 2b: Create second-level autofs executable script (handles HASH -> squashfs mount)
        auto_cefs_sub_script = f"""#!/bin/bash
key="$1"
subdir="${{key:0:2}}"
echo "-fstype=squashfs,loop,nosuid,nodev,ro :{cefs_image_dir}/${{subdir}}/${{key}}.sqfs"
"""
        run_cmd(
            ["sudo", "bash", "-c", f"cat > /etc/auto.cefs.sub << 'EOF'\n{auto_cefs_sub_script}EOF"],
            "Creating /etc/auto.cefs.sub script",
        )
        run_cmd(["sudo", "chmod", "+x", "/etc/auto.cefs.sub"], "Making /etc/auto.cefs.sub executable")

        # Step 3: Create autofs master entry
        auto_master_content = f"{cefs_mount_point} /etc/auto.cefs --negative-timeout 1"
        run_cmd(["sudo", "mkdir", "-p", "/etc/auto.master.d"], "Creating /etc/auto.master.d directory")
        run_cmd(
            ["sudo", "bash", "-c", f"echo '{auto_master_content}' > /etc/auto.master.d/cefs.autofs"],
            "Creating /etc/auto.master.d/cefs.autofs",
        )

        # Step 4: Restart autofs service
        run_cmd(["sudo", "service", "autofs", "restart"], "Restarting autofs service")

        # Step 5: Validate setup (only in real mode)
        if not dry_run:
            _LOGGER.info("Validating CEFS setup...")
            if validate_cefs_mount_point(cefs_mount_point):
                _LOGGER.info("CEFS setup completed successfully")
            else:
                raise click.ClickException("CEFS setup validation failed")
        else:
            _LOGGER.info("Would validate CEFS mount point: %s", cefs_mount_point)

    except subprocess.CalledProcessError as e:
        _LOGGER.error("Failed to set up CEFS: %s", e)
        raise click.ClickException(f"CEFS setup failed: {e}") from e
    except Exception as e:
        _LOGGER.error("Unexpected error during CEFS setup: %s", e)
        raise click.ClickException(f"CEFS setup failed: {e}") from e


@cefs.command()
@click.pass_obj
@click.argument("filter_", metavar="FILTER", nargs=-1)
def rollback(context: CliContext, filter_: list[str]):
    """Rollback CEFS conversions by restoring from .bak directories.

    This undoes CEFS conversions by:
    1. Removing the symlink
    2. Restoring the original directory from .bak
    3. Optionally cleaning up unused CEFS images
    """
    if not filter_:
        _LOGGER.error("No filter specified. Use a filter to select installables to rollback")
        raise click.ClickException("Filter required for safety")

    installables = context.get_installables(filter_)

    if not installables:
        _LOGGER.warning("No installables match filter: %s", " ".join(filter_))
        return

    successful = 0
    failed = 0
    skipped = 0
    rollback_details = []  # Track details for summary

    for installable in installables:
        # Only process installed installables
        if not installable.is_installed():
            _LOGGER.debug("Skipping %s - not installed", installable.name)
            skipped += 1
            continue

        nfs_path = context.installation_context.destination / installable.install_path
        backup_path = nfs_path.with_name(nfs_path.name + ".bak")

        _LOGGER.info("Rolling back %s...", installable.name)

        # Check if there's anything to rollback
        if not nfs_path.is_symlink():
            _LOGGER.info("Skipping %s - not a CEFS symlink", installable.name)
            skipped += 1
            continue

        if not backup_path.exists():
            _LOGGER.error("No backup found for %s at %s", installable.name, backup_path)
            failed += 1
            continue

        # Track where the symlink points for reporting
        try:
            symlink_target_str = str(nfs_path.readlink())
        except OSError:
            symlink_target_str = "<unable to read>"

        if context.installation_context.dry_run:
            _LOGGER.info(
                "Would rollback %s: remove symlink %s -> %s, restore from %s",
                installable.name,
                nfs_path,
                symlink_target_str,
                backup_path,
            )
            rollback_details.append({
                "name": installable.name,
                "status": "would_rollback",
                "symlink_target": symlink_target_str,
                "nfs_path": str(nfs_path),
            })
            successful += 1
            continue

        try:
            # Remove symlink
            _LOGGER.info("Removing CEFS symlink: %s -> %s", nfs_path, symlink_target_str or "<unable to read>")
            nfs_path.unlink()

            # Restore from backup
            _LOGGER.info("Restoring from backup: %s -> %s", backup_path, nfs_path)
            backup_path.rename(nfs_path)

            # Verify restoration
            if installable.is_installed():
                _LOGGER.info("Successfully rolled back %s", installable.name)
                rollback_details.append({
                    "name": installable.name,
                    "status": "success",
                    "symlink_target": symlink_target_str,
                    "nfs_path": str(nfs_path),
                })
                successful += 1
            else:
                _LOGGER.error("Rollback validation failed for %s", installable.name)
                rollback_details.append({
                    "name": installable.name,
                    "status": "validation_failed",
                    "symlink_target": symlink_target_str,
                    "nfs_path": str(nfs_path),
                })
                failed += 1

        except OSError as e:
            _LOGGER.error("Failed to rollback %s: %s", installable.name, e)
            rollback_details.append({
                "name": installable.name,
                "status": "failed",
                "symlink_target": symlink_target_str,
                "nfs_path": str(nfs_path),
                "error": str(e),
            })
            failed += 1

    # Detailed summary
    _LOGGER.info("Rollback complete: %d successful, %d failed, %d skipped", successful, failed, skipped)

    if rollback_details:
        _LOGGER.info("Rollback details:")
        for detail in rollback_details:
            if detail["status"] in ("success", "would_rollback"):
                _LOGGER.info("  %s: %s (symlink was: %s)", detail["name"], detail["status"], detail["symlink_target"])
            else:
                error_msg = f" - {detail.get('error', '')}" if detail.get("error") else ""
                _LOGGER.info(
                    "  %s: %s (symlink was: %s)%s",
                    detail["name"],
                    detail["status"],
                    detail["symlink_target"],
                    error_msg,
                )

    if failed > 0:
        raise click.ClickException(f"Failed to rollback {failed} installables")


@dataclass(frozen=True)
class ConsolidationCandidate:
    """Represents an item that can be consolidated."""

    name: str
    nfs_path: Path
    squashfs_path: Path
    size: int
    extraction_path: Path = Path(".")
    from_reconsolidation: bool = False


def _should_reconsolidate_image(
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


def _extract_candidates_from_manifest(
    manifest: dict,
    image_path: Path,
    state: CEFSState,
    filter_: list[str],
    size: int,
) -> list[ConsolidationCandidate]:
    """Extract reconsolidation candidates from a consolidated image manifest.

    Args:
        manifest: Image manifest dictionary
        image_path: Path to the consolidated image
        state: CEFS state object
        filter_: Optional filter for selecting items
        size: Total size of the consolidated image

    Returns:
        List of consolidation candidates from this image
    """
    candidates = []
    contents = manifest.get("contents", [])

    for content in contents:
        if "destination" not in content or "name" not in content:
            raise ValueError(f"Malformed manifest entry missing required fields: {content}")

        dest_path = Path(content["destination"])

        # Check if this specific item is still referenced to this image
        current_target = get_current_symlink_target(dest_path, state.nfs_dir)

        if not _is_item_still_using_image(current_target, image_path):
            # This item has been replaced, skip it
            continue

        # Apply filter if provided
        if filter_ and not any(f in content["name"] for f in filter_):
            continue

        # Determine extraction path within the consolidated image
        if current_target and len(current_target.parts) > 4:
            extraction_path = Path(*current_target.parts[4:])
        else:
            extraction_path = Path(".")

        # Add as candidate for reconsolidation
        candidates.append(
            ConsolidationCandidate(
                name=content["name"],
                nfs_path=dest_path if dest_path.is_absolute() else state.nfs_dir / dest_path,
                squashfs_path=image_path,
                extraction_path=extraction_path,
                size=size // len(contents),  # Estimate size per item
                from_reconsolidation=True,
            )
        )

    return candidates


def _gather_reconsolidation_candidates(
    context: CliContext,
    efficiency_threshold: float,
    max_size_bytes: int,
    undersized_ratio: float,
    filter_: list[str],
) -> list[ConsolidationCandidate]:
    """Gather candidates from existing consolidated images for reconsolidation.

    Args:
        context: CLI context
        efficiency_threshold: Minimum efficiency to keep consolidated image (0.0-1.0)
        max_size_bytes: Maximum size for consolidated images
        filter_: Optional filter for selecting items

    Returns:
        List of candidate items from consolidated images that should be repacked
    """
    candidates = []

    # Initialize CEFS state to analyze existing images
    state = CEFSState(
        nfs_dir=context.installation_context.destination,
        cefs_image_dir=context.config.cefs.image_dir,
    )

    state.scan_cefs_images_with_manifests()
    state.check_symlink_references()

    # Check each consolidated image
    for _filename_stem, image_path in state.all_cefs_images.items():
        if not is_consolidated_image(image_path):
            continue

        # Calculate usage for this consolidated image
        usage = calculate_image_usage(image_path, state.image_references, state.nfs_dir)

        # Get image size
        try:
            size = image_path.stat().st_size
        except OSError:
            continue

        # Determine if this image should be reconsolidated
        should_reconsolidate, reason = _should_reconsolidate_image(
            usage, size, efficiency_threshold, max_size_bytes, undersized_ratio
        )

        if not should_reconsolidate:
            continue

        _LOGGER.info("Consolidated image %s marked for reconsolidation: %s", image_path.name, reason)

        # Get manifest to extract individual items
        manifest = read_manifest_from_alongside(image_path)
        if not manifest or "contents" not in manifest:
            _LOGGER.warning("Cannot reconsolidate %s: no manifest", image_path.name)
            continue

        # Extract candidates from this image's manifest
        image_candidates = _extract_candidates_from_manifest(manifest, image_path, state, filter_, size)
        candidates.extend(image_candidates)

    return candidates


@cefs.command()
@click.pass_obj
@click.option(
    "--max-size", default="20GB", metavar="SIZE", help="Maximum size per consolidated image (e.g., 20GB, 500M)"
)
@click.option("--min-items", default=3, metavar="N", help="Minimum items to justify consolidation")
@click.option(
    "--defer-backup-cleanup",
    is_flag=True,
    help="Rename old .bak directories to .DELETE_ME_<timestamp> instead of deleting them immediately",
)
@click.option(
    "--max-parallel-extractions",
    type=int,
    default=None,
    help="Maximum parallel extractions (default: CPU count)",
)
@click.option(
    "--include-reconsolidation/--no-reconsolidation",
    default=False,
    help="Include existing consolidated images for repacking (default: False)",
)
@click.option(
    "--efficiency-threshold",
    default=0.5,
    type=float,
    help="Only repack consolidated images below this efficiency (0.0-1.0, default: 0.5)",
)
@click.argument("filter_", metavar="[FILTER]", nargs=-1, required=False)
def consolidate(
    context: CliContext,
    max_size: str,
    min_items: int,
    defer_backup_cleanup: bool,
    max_parallel_extractions: int | None,
    include_reconsolidation: bool,
    efficiency_threshold: float,
    undersized_ratio: float,
    filter_: list[str],
):
    """Consolidate multiple CEFS images into larger consolidated images to reduce mount overhead.

    This command combines multiple individual squashfs images into larger consolidated images
    with subdirectories, reducing the total number of autofs mounts while maintaining
    content-addressable benefits.

    When --include-reconsolidation is used, also repacks:
    - Undersized consolidated images (smaller than max-size/4)
    - Partially used consolidated images (below efficiency threshold)

    FILTER can be used to select which items to consolidate (e.g., 'arm' for ARM compilers).
    """
    # TODO: Future work needed:
    # 1. Garbage collection of unused CEFS images (images no longer referenced by any symlinks)
    # 2. Re-consolidation of sparse consolidated images - if we consolidate X,Y,Z but later
    #    Y and Z are reinstalled individually, the consolidated image only serves X and should
    #    be considered for re-consolidation with other single-use images.
    # 3. Refactor this gargantuan function into testable functions.
    if not validate_cefs_mount_point(context.config.cefs.mount_point):
        _LOGGER.error("CEFS mount point validation failed. Run 'ce cefs setup' first.")
        raise click.ClickException("CEFS not properly configured")

    try:
        max_size_bytes = humanfriendly.parse_size(max_size, binary=True)
    except humanfriendly.InvalidSize as e:
        raise click.ClickException(str(e)) from e

    # Get all installables and filter for CEFS-converted ones
    all_installables = context.get_installables(filter_)
    cefs_items: list[ConsolidationCandidate] = []

    for installable in all_installables:
        if not installable.is_squashable:
            continue

        nfs_path = context.installation_context.destination / installable.install_path

        # Check if item is already CEFS-converted (symlink to /cefs/)
        if nfs_path.is_symlink():
            try:
                cefs_target = nfs_path.readlink()
            except OSError as e:
                _LOGGER.warning("Failed to read symlink %s: %s", nfs_path, e)
                continue
            if not cefs_target.is_relative_to(context.config.cefs.mount_point):
                _LOGGER.warning("Symlink %s does not point to CEFS mount: skipping", nfs_path)
                continue
            try:
                cefs_image_path, is_already_consolidated = parse_cefs_target(cefs_target, context.config.cefs.image_dir)
            except ValueError as e:
                _LOGGER.warning("Invalid CEFS target format for %s: %s", installable.name, e)
                continue

            if is_already_consolidated:
                if not include_reconsolidation:
                    _LOGGER.debug("Item %s already consolidated at %s", installable.name, cefs_target)
                    continue
                # For reconsolidation, we'll handle this separately below

            if not cefs_image_path.exists():
                _LOGGER.warning("CEFS image not found for %s: %s", installable.name, cefs_image_path)
                continue
            size = cefs_image_path.stat().st_size
            cefs_items.append(
                ConsolidationCandidate(
                    name=installable.name,
                    nfs_path=nfs_path,
                    squashfs_path=cefs_image_path,  # Use CEFS image
                    size=size,
                )
            )
            _LOGGER.debug(
                "Found CEFS item %s -> %s (%s)",
                installable.name,
                cefs_image_path,
                humanfriendly.format_size(size, binary=True),
            )

    # Add reconsolidation candidates if enabled
    if include_reconsolidation:
        _LOGGER.info("Gathering reconsolidation candidates...")
        recon_candidates = _gather_reconsolidation_candidates(
            context, efficiency_threshold, max_size_bytes, undersized_ratio, filter_
        )

        if recon_candidates:
            _LOGGER.info("Found %d items from consolidated images for reconsolidation", len(recon_candidates))
            # Reconsolidation candidates are already in the right format
            cefs_items.extend(recon_candidates)

    if not cefs_items:
        _LOGGER.warning("No CEFS items found matching filter: %s", " ".join(filter_) if filter_ else "all")
        return

    _LOGGER.info("Found %d total CEFS items for consolidation", len(cefs_items))

    # Sort by name for deterministic packing
    cefs_items.sort(key=lambda x: x.name)

    # Pack items into groups
    groups: list[list[ConsolidationCandidate]] = []
    current_group: list[ConsolidationCandidate] = []
    current_size = 0

    for item in cefs_items:
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
    else:
        _LOGGER.info("Final group has only %d items (< %d minimum), not consolidating", len(current_group), min_items)

    if not groups:
        _LOGGER.warning("No groups meet consolidation criteria (min %d items, max %s per group)", min_items, max_size)
        return

    _LOGGER.info("Created %d consolidation groups", len(groups))

    # Calculate space requirements (5x largest group size since we process sequentially)
    largest_group_size = max(sum(item.size for item in group) for group in groups)
    total_compressed_size = sum(sum(item.size for item in group) for group in groups)
    required_temp_space = largest_group_size * 5

    # Show consolidation plan
    for i, group in enumerate(groups):
        group_size = sum(item.size for item in group)
        _LOGGER.info(
            "Group %d: %d items, %s compressed", i + 1, len(group), humanfriendly.format_size(group_size, binary=True)
        )
        if _LOGGER.isEnabledFor(logging.DEBUG):
            for item in group:
                _LOGGER.debug("  - %s (%s)", item.name, humanfriendly.format_size(item.size, binary=True))

    _LOGGER.info("Total compressed size: %s", humanfriendly.format_size(total_compressed_size, binary=True))
    _LOGGER.info(
        "Required temp space: %s (5x largest group: %s)",
        humanfriendly.format_size(required_temp_space, binary=True),
        humanfriendly.format_size(largest_group_size, binary=True),
    )

    # Check available space
    temp_dir = context.config.cefs.local_temp_dir
    temp_dir.mkdir(parents=True, exist_ok=True)
    if not check_temp_space_available(temp_dir, required_temp_space):
        available_stat = temp_dir.stat() if temp_dir.exists() else None
        if available_stat:
            stat = os.statvfs(temp_dir)
            available = stat.f_bavail * stat.f_frsize
            _LOGGER.error(
                "Insufficient temp space. Required: %s, Available: %s",
                humanfriendly.format_size(required_temp_space, binary=True),
                humanfriendly.format_size(available, binary=True),
            )
        else:
            _LOGGER.error("Temp directory does not exist: %s", temp_dir)
        raise click.ClickException("Insufficient disk space for consolidation")

    if context.installation_context.dry_run:
        _LOGGER.info("DRY RUN: Would consolidate %d groups", len(groups))
        return

    # Snapshot all symlinks before starting
    all_symlinks = [item.nfs_path for group in groups for item in group]
    symlink_snapshot = snapshot_symlink_targets(all_symlinks)
    _LOGGER.info("Snapshotted %d symlinks", len(symlink_snapshot))

    # Create unique directory for this consolidation run
    consolidation_dir = temp_dir / str(uuid.uuid4())
    consolidation_dir.mkdir(parents=True, exist_ok=True)

    # Process each group
    successful_groups = 0
    failed_groups = 0
    total_updated_symlinks = 0
    total_skipped_symlinks = 0

    for group_idx, group in enumerate(groups):
        _LOGGER.info("Processing group %d/%d (%d items)", group_idx + 1, len(groups), len(group))

        try:
            # Create temp directory for this group
            group_temp_dir = consolidation_dir / "extract"
            group_temp_dir.mkdir(parents=True, exist_ok=True)

            # Prepare items for consolidation - follow symlinks to determine extraction paths
            items_for_consolidation = []
            subdir_mapping = {}

            for item in group:
                # Use the installable name as subdirectory name (sanitized for filesystem)
                subdir_name = sanitize_path_for_filename(Path(item.name))

                # For reconsolidation items, we already have the extraction path
                if item.from_reconsolidation:
                    extraction_path = item.extraction_path
                    _LOGGER.debug(
                        "For reconsolidation item %s: using extraction path %s",
                        item.name,
                        extraction_path,
                    )
                else:
                    symlink_target = item.nfs_path.readlink()
                    extraction_path = get_extraction_path_from_symlink(symlink_target)
                    _LOGGER.debug(
                        "For %s: symlink %s -> %s, extracting %s",
                        item.name,
                        item.nfs_path,
                        symlink_target,
                        extraction_path,
                    )

                items_for_consolidation.append((item.nfs_path, item.squashfs_path, subdir_name, extraction_path))
                subdir_mapping[item.nfs_path] = subdir_name

            contents = [create_installable_manifest_entry(item.name, item.nfs_path) for item in group]

            manifest = create_manifest(
                operation="consolidate",
                description=f"Created through consolidation of {len(group)} items: "
                + ", ".join(item.name for item in group),
                contents=contents,
            )

            # Create temporary consolidated image with manifest
            temp_consolidated_path = group_temp_dir / "consolidated.sqfs"

            # First create basic consolidated image, then add manifest
            create_consolidated_image(
                context.config.squashfs,
                items_for_consolidation,
                group_temp_dir,
                temp_consolidated_path,
                max_parallel_extractions,
            )

            filename = get_cefs_filename_for_image(temp_consolidated_path, "consolidate")
            cefs_paths = get_cefs_paths(context.config.cefs.image_dir, context.config.cefs.mount_point, filename)

            if cefs_paths.image_path.exists():
                _LOGGER.info("Consolidated image already exists: %s", cefs_paths.image_path)
            else:
                deploy_to_cefs_with_manifest(temp_consolidated_path, cefs_paths.image_path, manifest)

            # Verify symlinks haven't changed and update them
            group_symlinks = [item.nfs_path for item in group]
            group_snapshot = {k: v for k, v in symlink_snapshot.items() if k in group_symlinks}
            unchanged_symlinks, changed_symlinks = verify_symlinks_unchanged(group_snapshot)

            if changed_symlinks:
                _LOGGER.warning("Skipping %d symlinks that changed during consolidation:", len(changed_symlinks))
                for symlink in changed_symlinks:
                    _LOGGER.warning("  - %s", symlink)
                total_skipped_symlinks += len(changed_symlinks)

            if unchanged_symlinks:
                update_symlinks_for_consolidation(
                    unchanged_symlinks, filename, context.config.cefs.mount_point, subdir_mapping, defer_backup_cleanup
                )
                total_updated_symlinks += len(unchanged_symlinks)
                _LOGGER.info("Updated %d symlinks for group %d", len(unchanged_symlinks), group_idx + 1)

            successful_groups += 1

        except RuntimeError as e:
            group_items = ", ".join(item.name for item in group)
            _LOGGER.error("Failed to consolidate group %d (%s): %s", group_idx + 1, group_items, e)
            _LOGGER.debug("Full error details:", exc_info=True)
            failed_groups += 1

        finally:
            # Clean up group temp directory
            if group_temp_dir.exists():
                shutil.rmtree(group_temp_dir)

    _LOGGER.info("Consolidation complete:")
    _LOGGER.info("  Successful groups: %d", successful_groups)
    _LOGGER.info("  Failed groups: %d", failed_groups)
    _LOGGER.info("  Updated symlinks: %d", total_updated_symlinks)
    _LOGGER.info("  Skipped symlinks: %d", total_skipped_symlinks)

    # Clean up consolidation directory
    if consolidation_dir.exists():
        shutil.rmtree(consolidation_dir)

    if failed_groups > 0:
        raise click.ClickException(f"Failed to consolidate {failed_groups} groups")


@cefs.command()
@click.pass_obj
@click.option("--force", is_flag=True, help="Skip confirmation prompt")
@click.option("--min-age", default="1h", help="Minimum age of images to consider for deletion (e.g., 1h, 30m, 1d)")
def gc(context: CliContext, force: bool, min_age: str):
    """Garbage collect unreferenced CEFS images using manifests.

    Reads manifest files from CEFS images to determine expected symlink locations,
    then checks if those symlinks exist and point back to the images.
    Images without valid references are marked for deletion.

    Images with .yaml.inprogress manifests are NEVER deleted (incomplete operations).
    """
    _LOGGER.info("Starting CEFS garbage collection using manifest system...")

    try:
        min_age_seconds = humanfriendly.parse_timespan(min_age)
        min_age_delta = datetime.timedelta(seconds=min_age_seconds)
        _LOGGER.info("Minimum age for deletion: %s", min_age)
    except humanfriendly.InvalidTimespan as e:
        raise click.ClickException(f"Invalid min-age: {e}") from e

    now = datetime.datetime.now()
    error_count = 0

    state = CEFSState(
        nfs_dir=context.installation_context.destination,
        cefs_image_dir=context.config.cefs.image_dir,
    )

    _LOGGER.info("Scanning CEFS images directory and reading manifests...")
    state.scan_cefs_images_with_manifests()

    _LOGGER.info("Checking symlink references...")
    state.check_symlink_references()

    if state.inprogress_images:
        _LOGGER.warning("Found %d in-progress operations (these will NOT be deleted):", len(state.inprogress_images))
        for inprogress_path in state.inprogress_images:
            try:
                mtime = datetime.datetime.fromtimestamp(inprogress_path.stat().st_mtime)
                age = now - mtime
                age_str = humanfriendly.format_timespan(age.total_seconds())
                _LOGGER.warning("  %s (age: %s)", inprogress_path, age_str)
            except OSError as e:
                _LOGGER.warning("  %s (could not get age: %s)", inprogress_path, e)

    # Report broken images that need investigation
    if state.broken_images:
        _LOGGER.error("")
        _LOGGER.error("=" * 60)
        _LOGGER.error("CRITICAL: Found %d broken images without manifests", len(state.broken_images))
        _LOGGER.error("These require manual investigation:")
        for broken_image in state.broken_images:
            _LOGGER.error("  - %s", broken_image)
        _LOGGER.error("=" * 60)
        _LOGGER.error("")

    summary = state.get_summary()
    _LOGGER.info("CEFS GC Summary:")
    _LOGGER.info("  Total CEFS images: %d", summary.total_images)
    _LOGGER.info("  Referenced images: %d", summary.referenced_images)
    _LOGGER.info("  Unreferenced images: %d", summary.unreferenced_images)
    _LOGGER.info("  Space to reclaim: %s", humanfriendly.format_size(summary.space_to_reclaim, binary=True))

    filter_result = filter_images_by_age(state.find_unreferenced_images(), min_age_delta, now)
    unreferenced = filter_result.old_enough

    for image_path, age in filter_result.too_recent:
        _LOGGER.info(
            "Skipping recent image (age %s): %s", humanfriendly.format_timespan(age.total_seconds()), image_path
        )

    if not unreferenced:
        _LOGGER.info("No unreferenced CEFS images found. Nothing to clean up.")
        if error_count > 0:
            raise click.ClickException(f"GC completed with {error_count} errors during analysis")
        return

    _LOGGER.info("Unreferenced CEFS images to delete:")
    for image_path in unreferenced:
        try:
            size_str = humanfriendly.format_size(image_path.stat().st_size, binary=True)
        except OSError:
            size_str = "size unknown"
            error_count += 1
            _LOGGER.error("Could not stat image: %s", image_path)
        _LOGGER.info(
            "  %s (%s)%s",
            image_path,
            size_str,
            format_image_contents_string(get_image_description(image_path, context.config.cefs.mount_point), 3)
            or " [contents unknown]",
        )

    if context.installation_context.dry_run:
        _LOGGER.info("DRY RUN: Would delete %d unreferenced images", len(unreferenced))
        if error_count > 0:
            raise click.ClickException(f"GC completed with {error_count} errors during analysis")
        return

    if not force and not click.confirm(f"Delete {len(unreferenced)} unreferenced CEFS images?"):
        _LOGGER.info("Garbage collection cancelled by user")
        return

    deleted_count = 0
    deleted_size = 0
    _LOGGER.info("Performing double-check before deletion...")

    for image_path in unreferenced:
        # SAFETY: Double-check - Re-verify the image is still unreferenced immediately before deletion, by
        # checking no symlinks now point to this image. This guards against race conditions where another
        # process creates a symlink between our initial scan and the deletion attempt. Since we have no locking,
        # this is our last line of defense against deleting an image that just became referenced.
        try:
            if state.is_image_referenced(image_path.stem):
                _LOGGER.warning("Double-check: Image %s is now referenced, skipping deletion", image_path)
                continue
        except ValueError as e:
            # This shouldn't happen - unreferenced images should all be in image_references
            _LOGGER.error("Error during double-check for %s: %s", image_path, e)
            continue  # Skip deletion to be safe

        result = delete_image_with_manifest(image_path)
        if result.success:
            deleted_count += 1
            deleted_size += result.deleted_size
            _LOGGER.info("Deleted: %s", image_path)
            for error in result.errors:
                _LOGGER.warning(error)
        else:
            error_count += 1
            for error in result.errors:
                _LOGGER.error(error)

    _LOGGER.info(
        "Garbage collection complete: deleted %d images, freed %s",
        deleted_count,
        humanfriendly.format_size(deleted_size, binary=True),
    )

    if error_count > 0:
        raise click.ClickException(f"GC completed with {error_count} errors")
