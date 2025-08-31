#!/usr/bin/env python3
"""CEFS (Compiler Explorer FileSystem) v2 commands."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import uuid
from typing import Any

import click
import humanfriendly

from lib.ce_install import CliContext, cli
from lib.cefs import (
    CEFSState,
    backup_and_symlink,
    check_temp_space_available,
    create_consolidated_image,
    deploy_to_cefs_with_manifest,
    describe_cefs_image,
    detect_nfs_state,
    get_cefs_filename_for_image,
    get_cefs_paths,
    get_extraction_path_from_symlink,
    parse_cefs_target,
    snapshot_symlink_targets,
    update_symlinks_for_consolidation,
    validate_cefs_mount_point,
    verify_symlinks_unchanged,
)
from lib.cefs_manifest import (
    create_installable_manifest_entry,
    create_manifest,
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
    if not cefs_paths.image_path.exists():
        if context.installation_context.dry_run:
            _LOGGER.info("Would copy %s to %s", squashfs_image_path, cefs_paths.image_path)
            _LOGGER.info("Would write manifest alongside image")
        else:
            try:
                deploy_to_cefs_with_manifest(squashfs_image_path, cefs_paths.image_path, manifest)
            except Exception as e:
                _LOGGER.error("Failed to deploy image for %s: %s", installable.name, e)
                return False
    else:
        _LOGGER.info("CEFS image already exists: %s", cefs_paths.image_path)

    # Backup NFS directory and create symlink
    try:
        backup_and_symlink(nfs_path, cefs_paths.mount_path, context.installation_context.dry_run, defer_cleanup)
    except RuntimeError as e:
        _LOGGER.error("Failed to create symlink for %s: %s", installable.name, e)
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


@cefs.command()
@click.pass_obj
def status(context):
    """Show CEFS configuration status."""
    print("CEFS Configuration:")
    print(f"  Enabled: {context.config.cefs.enabled}")
    print(f"  Mount Point: {context.config.cefs.mount_point}")
    print(f"  Image Directory: {context.config.cefs.image_dir}")
    print(f"  Local Temp Directory: {context.config.cefs.local_temp_dir}")
    print("Squashfs Configuration:")
    print(f"  Traditional Enabled: {context.config.squashfs.traditional_enabled}")
    print(f"  Compression: {context.config.squashfs.compression}")
    print(f"  Compression Level: {context.config.squashfs.compression_level}")


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
            rollback_details.append(
                {
                    "name": installable.name,
                    "status": "would_rollback",
                    "symlink_target": symlink_target_str,
                    "nfs_path": str(nfs_path),
                }
            )
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
                rollback_details.append(
                    {
                        "name": installable.name,
                        "status": "success",
                        "symlink_target": symlink_target_str,
                        "nfs_path": str(nfs_path),
                    }
                )
                successful += 1
            else:
                _LOGGER.error("Rollback validation failed for %s", installable.name)
                rollback_details.append(
                    {
                        "name": installable.name,
                        "status": "validation_failed",
                        "symlink_target": symlink_target_str,
                        "nfs_path": str(nfs_path),
                    }
                )
                failed += 1

        except OSError as e:
            _LOGGER.error("Failed to rollback %s: %s", installable.name, e)
            rollback_details.append(
                {
                    "name": installable.name,
                    "status": "failed",
                    "symlink_target": symlink_target_str,
                    "nfs_path": str(nfs_path),
                    "error": str(e),
                }
            )
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


@cefs.command()
@click.pass_obj
@click.option(
    "--max-size", default="2GB", metavar="SIZE", help="Maximum size per consolidated image (e.g., 2GB, 500M, 10G)"
)
@click.option("--min-items", default=3, metavar="N", help="Minimum items to justify consolidation")
@click.option(
    "--defer-backup-cleanup",
    is_flag=True,
    help="Rename old .bak directories to .DELETE_ME_<timestamp> instead of deleting them immediately",
)
@click.argument("filter_", metavar="[FILTER]", nargs=-1, required=False)
def consolidate(context: CliContext, max_size: str, min_items: int, defer_backup_cleanup: bool, filter_: list[str]):
    """Consolidate multiple CEFS images into larger consolidated images to reduce mount overhead.

    This command combines multiple individual squashfs images into larger consolidated images
    with subdirectories, reducing the total number of autofs mounts while maintaining
    content-addressable benefits.

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
    cefs_items: list[dict[str, Any]] = []

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
                _LOGGER.debug("Item %s already consolidated at %s", installable.name, cefs_target)
                continue

            if not cefs_image_path.exists():
                _LOGGER.warning("CEFS image not found for %s: %s", installable.name, cefs_image_path)
                continue
            size = cefs_image_path.stat().st_size
            cefs_items.append(
                {
                    "installable": installable,
                    "nfs_path": nfs_path,
                    "squashfs_path": cefs_image_path,  # Use CEFS image
                    "size": size,
                }
            )
            _LOGGER.debug(
                "Found CEFS item %s -> %s (%s)",
                installable.name,
                cefs_image_path,
                humanfriendly.format_size(size, binary=True),
            )

    if not cefs_items:
        _LOGGER.warning("No CEFS items found matching filter: %s", " ".join(filter_) if filter_ else "all")
        return

    _LOGGER.info("Found %d CEFS items", len(cefs_items))

    # Sort by name for deterministic packing
    cefs_items.sort(key=lambda x: x["installable"].name)

    # Pack items into groups
    groups: list[list[dict[str, Any]]] = []
    current_group: list[dict[str, Any]] = []
    current_size = 0

    for item in cefs_items:
        if current_size + item["size"] > max_size_bytes and len(current_group) >= min_items:
            # Start new group
            groups.append(current_group)
            current_group = [item]
            current_size = item["size"]
        else:
            current_group.append(item)
            current_size += item["size"]

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
    largest_group_size = max(sum(item["size"] for item in group) for group in groups)
    total_compressed_size = sum(sum(item["size"] for item in group) for group in groups)
    required_temp_space = largest_group_size * 5

    # Show consolidation plan
    for i, group in enumerate(groups):
        group_size = sum(item["size"] for item in group)
        _LOGGER.info(
            "Group %d: %d items, %s compressed", i + 1, len(group), humanfriendly.format_size(group_size, binary=True)
        )
        if _LOGGER.isEnabledFor(logging.DEBUG):
            for item in group:
                _LOGGER.debug(
                    "  - %s (%s)", item["installable"].name, humanfriendly.format_size(item["size"], binary=True)
                )

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
    all_symlinks = [item["nfs_path"] for group in groups for item in group]
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
                # Use the installable name as subdirectory name
                subdir_name = item["installable"].name.replace("/", "_").replace(" ", "_")

                symlink_target = item["nfs_path"].readlink()
                extraction_path = get_extraction_path_from_symlink(symlink_target)
                _LOGGER.debug(
                    "For %s: symlink %s -> %s, extracting %s",
                    item["installable"].name,
                    item["nfs_path"],
                    symlink_target,
                    extraction_path,
                )

                items_for_consolidation.append((item["nfs_path"], item["squashfs_path"], subdir_name, extraction_path))
                subdir_mapping[item["nfs_path"]] = subdir_name

            contents = [create_installable_manifest_entry(item["installable"].name, item["nfs_path"]) for item in group]

            manifest = create_manifest(
                operation="consolidate",
                description=f"Created through consolidation of {len(group)} items: "
                + ", ".join(item["installable"].name for item in group),
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
            )

            filename = get_cefs_filename_for_image(temp_consolidated_path, "consolidate")
            cefs_paths = get_cefs_paths(context.config.cefs.image_dir, context.config.cefs.mount_point, filename)

            if cefs_paths.image_path.exists():
                _LOGGER.info("Consolidated image already exists: %s", cefs_paths.image_path)
            else:
                deploy_to_cefs_with_manifest(temp_consolidated_path, cefs_paths.image_path, manifest)

            # Verify symlinks haven't changed and update them
            group_symlinks = [item["nfs_path"] for item in group]
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
            group_items = ", ".join(item["installable"].name for item in group)
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
def gc(context: CliContext, force: bool):
    """Garbage collect unreferenced CEFS images.

    Scans all installables (including nightly/non-free) and their .bak versions
    to find all referenced CEFS images, then identifies and removes unreferenced ones.
    """
    _LOGGER.info("Starting CEFS garbage collection...")

    # Track errors throughout the function
    error_count = 0

    # Create state tracker
    state = CEFSState(
        nfs_dir=context.installation_context.destination,
        cefs_image_dir=context.config.cefs.image_dir,
    )

    # Get ALL installables (bypassing if: conditions)
    _LOGGER.info("Getting all installables...")
    all_installables = context.get_installables([], bypass_enable_check=True)
    _LOGGER.info("Found %d installables to check", len(all_installables))

    # Scan for CEFS references
    _LOGGER.info("Scanning installables for CEFS references...")
    state.scan_installables(all_installables)

    # Scan CEFS images directory
    _LOGGER.info("Scanning CEFS images directory...")
    state.scan_cefs_images()

    # Get summary
    summary = state.get_summary()
    _LOGGER.info("CEFS GC Summary:")
    _LOGGER.info("  Total CEFS images: %d", summary["total_images"])
    _LOGGER.info("  Referenced images: %d", summary["referenced_images"])
    _LOGGER.info("  Unreferenced images: %d", summary["unreferenced_images"])

    if summary["space_to_reclaim"] > 0:
        _LOGGER.info("  Space to reclaim: %s", humanfriendly.format_size(summary["space_to_reclaim"], binary=True))

    # Find unreferenced images
    unreferenced = state.find_unreferenced_images()

    if not unreferenced:
        _LOGGER.info("No unreferenced CEFS images found. Nothing to clean up.")
        if error_count > 0:
            raise click.ClickException(f"GC completed with {error_count} errors during analysis")
        return

    # List what would be deleted with descriptions
    _LOGGER.info("Unreferenced CEFS images to delete:")
    for image_path in unreferenced:
        try:
            size = image_path.stat().st_size
            size_str = humanfriendly.format_size(size, binary=True)
        except OSError:
            size_str = "size unknown"
            error_count += 1
            _LOGGER.error("Could not stat image: %s", image_path)

        # Get hash from filename for description
        hash_value = image_path.stem
        contents = describe_cefs_image(hash_value, context.config.cefs.mount_point)
        if contents:
            contents_str = f" [contains: {', '.join(contents)}]"
        else:
            contents_str = " [contents unknown]"

        _LOGGER.info("  %s (%s)%s", image_path, size_str, contents_str)

    # Handle dry-run
    if context.installation_context.dry_run:
        _LOGGER.info("DRY RUN: Would delete %d unreferenced images", len(unreferenced))
        if error_count > 0:
            raise click.ClickException(f"GC completed with {error_count} errors during analysis")
        return

    # Confirm deletion
    if not force:
        if not click.confirm(f"Delete {len(unreferenced)} unreferenced CEFS images?"):
            _LOGGER.info("Garbage collection cancelled by user")
            return

    # Delete unreferenced images
    deleted_count = 0
    deleted_size = 0
    for image_path in unreferenced:
        try:
            size = image_path.stat().st_size
            image_path.unlink()
            deleted_count += 1
            deleted_size += size
            _LOGGER.info("Deleted: %s", image_path)
        except OSError as e:
            error_count += 1
            _LOGGER.error("Failed to delete %s: %s", image_path, e)

    _LOGGER.info(
        "Garbage collection complete: deleted %d images, freed %s",
        deleted_count,
        humanfriendly.format_size(deleted_size, binary=True) if deleted_size > 0 else "0 bytes",
    )

    # Exit with error if there were problems
    if error_count > 0:
        raise click.ClickException(f"GC completed with {error_count} errors")
