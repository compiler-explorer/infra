#!/usr/bin/env python3
"""CEFS (Compiler Explorer FileSystem) v2 commands."""

from __future__ import annotations

import datetime
import logging
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import click
import humanfriendly

from lib.ce_install import CliContext, cli
from lib.cefs.consolidation import (
    ConsolidationCandidate,
    pack_items_into_groups,
    process_consolidation_group,
    validate_space_requirements,
)
from lib.cefs.conversion import convert_to_cefs
from lib.cefs.deployment import snapshot_symlink_targets
from lib.cefs.formatting import (
    format_image_contents_string,
    format_usage_statistics,
    get_image_description,
    get_installable_current_locations,
)
from lib.cefs.fsck import FSCKResults, run_fsck_validation
from lib.cefs.gc import delete_image_with_manifest, filter_images_by_age
from lib.cefs.paths import FileWithAge, parse_cefs_target, validate_cefs_mount_point
from lib.cefs.state import CEFSState

_LOGGER = logging.getLogger(__name__)


@cli.group()
def cefs():
    """CEFS (Compiler Explorer FileSystem) v2 commands."""


def _print_basic_config(context: CliContext) -> None:
    """Print basic CEFS and Squashfs configuration."""
    click.echo("CEFS Configuration:")
    click.echo(f"  Enabled: {context.config.cefs.enabled}")
    click.echo(f"  Mount Point: {context.config.cefs.mount_point}")
    click.echo(f"  Image Directory: {context.config.cefs.image_dir}")
    click.echo(f"  Local Temp Directory: {context.config.cefs.local_temp_dir}")
    click.echo("Squashfs Configuration:")
    click.echo(f"  Traditional Enabled: {context.config.squashfs.traditional_enabled}")
    click.echo(f"  Compression: {context.config.squashfs.compression}")
    click.echo(f"  Compression Level: {context.config.squashfs.compression_level}")


@cefs.command()
@click.pass_obj
@click.option("--show-usage", is_flag=True, help="Show detailed usage statistics for CEFS images")
@click.option("--verbose", is_flag=True, help="Show per-image details when using --show-usage")
def status(context, show_usage: bool, verbose: bool):
    """Show CEFS configuration status."""
    _print_basic_config(context)

    if not show_usage:
        return

    click.echo("\nCEFS Image Usage Statistics:")
    click.echo("  Scanning images and checking references...")

    state = CEFSState(
        nfs_dir=context.installation_context.destination,
        cefs_image_dir=context.config.cefs.image_dir,
        mount_point=context.config.cefs.mount_point,
    )

    state.scan_cefs_images_with_manifests()
    state.check_symlink_references()

    stats = state.get_usage_stats()
    output_lines = format_usage_statistics(stats, state, verbose, context.config.cefs.mount_point)
    for line in output_lines:
        click.echo(line)


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
        squashfs_image_path = context.config.squashfs.image_dir / f"{installable.install_path}.img"
        if convert_to_cefs(
            installable,
            context.installation_context.destination,
            squashfs_image_path,
            context.config.squashfs,
            context.config.cefs,
            force,
            defer_backup_cleanup,
            context.installation_context.dry_run,
        ):
            successful += 1
        else:
            failed += 1

    _LOGGER.info("Conversion complete: %d successful, %d failed, %d skipped", successful, failed, skipped)

    if failed > 0:
        raise click.ClickException(f"Failed to convert {failed} installables")


def _run_setup_command(cmd: list[str], description: str, dry_run: bool) -> None:
    """Run command or show what would be run in dry-run mode.

    Args:
        cmd: Command to run
        description: Description of what the command does
        dry_run: If True, just log what would be run
    """
    if dry_run:
        _LOGGER.info("Would run: %s", " ".join(cmd))
    else:
        _LOGGER.info("%s", description)
        subprocess.check_call(cmd)


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

    _LOGGER.info("Setting up CEFS autofs configuration")
    _LOGGER.info("Mount point: %s", cefs_mount_point)
    _LOGGER.info("Image directory: %s", cefs_image_dir)

    if dry_run:
        _LOGGER.info("DRY RUN mode - showing commands that would be executed:")

    # IMPORTANT: any changes to this setup should be reflected in the setup_cefs
    # bash script in setup-common.sh (and vice versa).
    try:
        # Step 1: Create CEFS mount point
        _run_setup_command(
            ["sudo", "mkdir", "-p", str(cefs_mount_point)], f"Creating CEFS mount point: {cefs_mount_point}", dry_run
        )

        # Step 2: Create first-level autofs map file (handles {mount_point}/XX -> nested autofs)
        # Use the mount point name for autofs config files (e.g., /cefs -> auto.cefs, /test/mount -> auto.mount)
        auto_config_base = f"/etc/auto.{cefs_mount_point.name}"
        auto_cefs_content = f"* -fstype=autofs program:{auto_config_base}.sub"
        _run_setup_command(
            ["sudo", "bash", "-c", f"echo '{auto_cefs_content}' > {auto_config_base}"],
            f"Creating {auto_config_base}",
            dry_run,
        )

        # Step 2b: Create second-level autofs executable script (handles HASH -> squashfs mount)
        auto_cefs_sub_script = f"""#!/bin/bash
key="$1"
subdir="${{key:0:2}}"
echo "-fstype=squashfs,loop,nosuid,nodev,ro :{cefs_image_dir}/${{subdir}}/${{key}}.sqfs"
"""
        _run_setup_command(
            ["sudo", "bash", "-c", f"cat > {auto_config_base}.sub << 'EOF'\n{auto_cefs_sub_script}EOF"],
            f"Creating {auto_config_base}.sub script",
            dry_run,
        )
        _run_setup_command(
            ["sudo", "chmod", "+x", f"{auto_config_base}.sub"], f"Making {auto_config_base}.sub executable", dry_run
        )

        # Step 3: Create autofs master entry
        auto_master_content = f"{cefs_mount_point} {auto_config_base} --negative-timeout 1"
        _run_setup_command(
            ["sudo", "mkdir", "-p", "/etc/auto.master.d"], "Creating /etc/auto.master.d directory", dry_run
        )
        _run_setup_command(
            ["sudo", "bash", "-c", f"echo '{auto_master_content}' > /etc/auto.master.d/{cefs_mount_point.name}.autofs"],
            f"Creating /etc/auto.master.d/{cefs_mount_point.name}.autofs",
            dry_run,
        )

        # Step 4: Restart autofs service
        _run_setup_command(["sudo", "service", "autofs", "restart"], "Restarting autofs service", dry_run)

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
        nfs_path = context.installation_context.destination / installable.install_path
        backup_path = nfs_path.with_name(nfs_path.name + ".bak")

        _LOGGER.info("Checking %s for rollback...", installable.name)

        # Check if this is a CEFS installation (symlink exists)
        if not nfs_path.exists(follow_symlinks=False):
            _LOGGER.debug("Skipping %s - path does not exist", installable.name)
            skipped += 1
            continue

        if not nfs_path.is_symlink():
            _LOGGER.debug("Skipping %s - not a CEFS symlink (is a regular directory/file)", installable.name)
            skipped += 1
            continue

        # Check if we can rollback (backup exists)
        if not backup_path.exists():
            _LOGGER.error("Cannot rollback %s - no backup found at %s", installable.name, backup_path)
            failed += 1
            continue

        _LOGGER.info("Rolling back %s...", installable.name)

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

            # Verify restoration - check that path exists (can be directory or symlink)
            # and that backup no longer exists (was successfully renamed)
            if nfs_path.exists() and not backup_path.exists():
                _LOGGER.info("Successfully rolled back %s", installable.name)
                rollback_details.append({
                    "name": installable.name,
                    "status": "success",
                    "symlink_target": symlink_target_str,
                    "nfs_path": str(nfs_path),
                })
                successful += 1
            else:
                _LOGGER.error("Rollback validation failed for %s - restoration incomplete", installable.name)
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
    "--reconsolidate/--no-reconsolidate",
    default=False,
    help="Include existing consolidated images for repacking (default: False)",
)
@click.option(
    "--efficiency-threshold",
    default=0.5,
    type=float,
    help="Only repack consolidated images below this efficiency (0.0-1.0, default: 0.5)",
)
@click.option(
    "--undersized-ratio",
    default=0.25,
    type=float,
    help="Consider consolidated images undersized if smaller than max-size * this ratio (default: 0.25)",
)
@click.argument("filter_", metavar="[FILTER]", nargs=-1, required=False)
def consolidate(
    context: CliContext,
    max_size: str,
    min_items: int,
    defer_backup_cleanup: bool,
    max_parallel_extractions: int | None,
    reconsolidate: bool,
    efficiency_threshold: float,
    undersized_ratio: float,
    filter_: list[str],
):
    """Consolidate multiple CEFS images into larger consolidated images to reduce mount overhead.

    This command combines multiple individual squashfs images into larger consolidated images
    with subdirectories, reducing the total number of autofs mounts while maintaining
    content-addressable benefits.

    When --reconsolidate is used, also repacks:
    - Undersized consolidated images (smaller than max-size/4)
    - Partially used consolidated images (below efficiency threshold)

    FILTER can be used to select which items to consolidate (e.g., 'arm' for ARM compilers).
    """
    if not validate_cefs_mount_point(context.config.cefs.mount_point):
        _LOGGER.error("CEFS mount point validation failed. Run 'ce cefs setup' first.")
        raise click.ClickException("CEFS not properly configured")

    try:
        max_size_bytes = humanfriendly.parse_size(max_size, binary=True)
    except humanfriendly.InvalidSize as e:
        raise click.ClickException(str(e)) from e

    all_installables = context.get_installables(filter_)
    cefs_items: list[ConsolidationCandidate] = []

    for installable in all_installables:
        if not installable.is_squashable:
            continue

        nfs_path = context.installation_context.destination / installable.install_path

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
                cefs_image_path, is_already_consolidated = parse_cefs_target(
                    cefs_target, context.config.cefs.image_dir, context.config.cefs.mount_point
                )
            except ValueError as e:
                _LOGGER.warning("Invalid CEFS target format for %s: %s", installable.name, e)
                continue

            if is_already_consolidated:
                if not reconsolidate:
                    _LOGGER.debug("Item %s already consolidated at %s", installable.name, cefs_target)
                    continue
                # For reconsolidation, we'll handle this separately below
                continue

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
    if reconsolidate:
        _LOGGER.info("Gathering reconsolidation candidates...")
        recon_state = CEFSState(
            nfs_dir=context.installation_context.destination,
            cefs_image_dir=context.config.cefs.image_dir,
            mount_point=context.config.cefs.mount_point,
        )
        recon_state.scan_cefs_images_with_manifests()
        recon_state.check_symlink_references()

        recon_candidates = recon_state.gather_reconsolidation_candidates(
            efficiency_threshold, max_size_bytes, undersized_ratio, filter_
        )

        if recon_candidates:
            _LOGGER.info("Found %d items from consolidated images for reconsolidation", len(recon_candidates))
            # Reconsolidation candidates are already in the right format
            cefs_items.extend(recon_candidates)

    if not cefs_items:
        _LOGGER.warning("No CEFS items found matching filter: %s", " ".join(filter_) if filter_ else "all")
        return

    _LOGGER.info("Found %d total CEFS items for consolidation", len(cefs_items))

    # Pack items into groups
    groups = pack_items_into_groups(cefs_items, max_size_bytes, min_items)

    if not groups:
        _LOGGER.warning("No groups meet consolidation criteria (min %d items, max %s per group)", min_items, max_size)
        return

    _LOGGER.info("Created %d consolidation groups", len(groups))

    temp_dir = context.config.cefs.local_temp_dir
    try:
        required_temp_space, largest_group_size = validate_space_requirements(groups, temp_dir)
    except RuntimeError as e:
        raise click.ClickException(str(e)) from e

    # Show consolidation plan
    total_compressed_size = sum(sum(item.size for item in group) for group in groups)
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

    if context.installation_context.dry_run:
        _LOGGER.info("DRY RUN: Would consolidate %d groups", len(groups))
        return

    # Snapshot all symlinks before starting
    all_symlinks = [item.nfs_path for group in groups for item in group]
    symlink_snapshot = snapshot_symlink_targets(all_symlinks)
    _LOGGER.info("Snapshotted %d symlinks", len(symlink_snapshot))

    consolidation_dir = temp_dir / str(uuid.uuid4())
    consolidation_dir.mkdir(parents=True, exist_ok=True)

    successful_groups = 0
    failed_groups = 0
    total_updated_symlinks = 0
    total_skipped_symlinks = 0

    for group_idx, group in enumerate(groups):
        _LOGGER.info("Processing group %d/%d (%d items)", group_idx + 1, len(groups), len(group))

        success, updated, skipped = process_consolidation_group(
            group,
            group_idx,
            context.config.squashfs,
            context.config.cefs.mount_point,
            context.config.cefs.image_dir,
            symlink_snapshot,
            consolidation_dir,
            defer_backup_cleanup,
            max_parallel_extractions,
            lambda name: context.find_installable_by_exact_name(name),
            context.installation_context.dry_run,
        )

        if success:
            successful_groups += 1
            total_updated_symlinks += updated
            total_skipped_symlinks += skipped
        else:
            failed_groups += 1

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
        mount_point=context.config.cefs.mount_point,
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
        _LOGGER.error("CRITICAL: Found %d broken images with missing or invalid manifests", len(state.broken_images))
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

        # Show where each Installable in this image is currently installed
        for line in get_installable_current_locations(image_path):
            _LOGGER.info(line)

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


def display_verbose_fsck_logs(
    state: CEFSState,
    results: FSCKResults,
) -> None:
    """Display verbose logging for fsck validation.

    Args:
        state: CEFS state with image information
        results: Validation results
    """
    for _stem, image_path in state.all_cefs_images.items():
        manifest_path = image_path.with_suffix(".yaml")
        if (
            manifest_path not in results.missing_manifests
            and manifest_path not in results.old_format_manifests
            and not any(m[0] == manifest_path for m in results.invalid_name_manifests)
            and not any(m[0] == manifest_path for m in results.other_invalid_manifests)
            and not any(m[0] == manifest_path for m in results.unreadable_manifests)
        ):
            click.echo(f"✅ Valid manifest: {manifest_path}")
        elif manifest_path in results.missing_manifests:
            click.echo(f"❌ Missing manifest for {image_path}")
        elif manifest_path in results.old_format_manifests:
            click.echo(f"❌ Old manifest format (has 'target' field): {manifest_path}")
        else:
            for m_path, error in results.invalid_name_manifests:
                if m_path == manifest_path:
                    click.echo(f"❌ Invalid manifest: {manifest_path}")
                    click.echo(f"   Reason: {error}")
                    break
            for m_path, error in results.other_invalid_manifests:
                if m_path == manifest_path:
                    click.echo(f"❌ Invalid manifest: {manifest_path}")
                    click.echo(f"   Reason: {error}")
                    break
            for m_path, error in results.unreadable_manifests:
                if m_path == manifest_path:
                    click.echo(f"❌ Cannot read manifest: {manifest_path}: {error}")
                    break

    for file_with_age in results.inprogress_files:
        age_str = humanfriendly.format_timespan(file_with_age.age_seconds)
        click.echo(f"  Found .inprogress file: {file_with_age.path} (age: {age_str})")

    for item_with_age in results.pending_backups:
        item_type = "symlink" if item_with_age.path.is_symlink() else "directory"
        age_str = humanfriendly.format_timespan(item_with_age.age_seconds)
        click.echo(f"  Found .bak {item_type}: {item_with_age.path} (age: {age_str})")
    for item_with_age in results.pending_deletes:
        item_type = "symlink" if item_with_age.path.is_symlink() else "directory"
        age_str = humanfriendly.format_timespan(item_with_age.age_seconds)
        click.echo(f"  Found .DELETE_ME {item_type}: {item_with_age.path} (age: {age_str})")


def format_cleanup_item(item: FileWithAge | tuple | Path) -> str:
    """Format a cleanup item for display.

    Args:
        item: Either a FileWithAge, tuple (path, age_str, age_hours), or a Path

    Returns:
        Formatted string for display
    """
    if isinstance(item, FileWithAge):
        age_str = humanfriendly.format_timespan(item.age_seconds)
        return f"    • {item.path} (age: {age_str})"
    elif isinstance(item, tuple):
        path, age_str, _ = item
        return f"    • {path} (age: {age_str})"
    return f"    • {item}"


def display_fsck_results(results: FSCKResults, verbose: bool) -> None:
    """Display FSCK results in a structured format.

    Args:
        results: FSCKResults object containing all validation results
        verbose: Whether to show verbose output
    """
    # Print organized summary
    click.echo("\n" + "=" * 60)
    click.echo("CEFS Filesystem Check Results")
    click.echo("=" * 60)

    # Quick summary
    click.echo("\n📊 Summary:")
    click.echo(f"  Total images scanned: {results.total_images}")
    click.echo(f"  ✅ Valid manifests: {results.valid_manifests}")
    click.echo(f"  ❌ Invalid/problematic: {results.total_invalid}")
    click.echo(f"  🔄 In-progress files: {len(results.inprogress_files)}")
    click.echo(f"  🗑️  Pending cleanup: {len(results.pending_backups) + len(results.pending_deletes)}")

    if not results.has_issues:
        click.echo("\n✅ All manifests are valid and symlinks are intact!")
        return

    # Detailed issues by category
    click.echo("\n📋 Issues by Category:")

    # Invalid names (most common issue)
    if results.invalid_name_manifests:
        click.echo(
            f"\n  Invalid Installable Names ({len(results.invalid_name_manifests)} manifest{'s' if len(results.invalid_name_manifests) > 1 else ''}):"
        )
        click.echo("  These manifests contain entries with improper naming format.")
        click.echo("  Expected format: 'category/subcategory/name version' (e.g., 'compilers/c++/x86/gcc 12.4.0')")
        for manifest_path, error in results.invalid_name_manifests[:3]:
            # Extract just the error details
            if "Invalid manifest:" in error:
                error = error.split("Invalid manifest:")[-1].strip()
            click.echo(f"    • {manifest_path}")
            click.echo(f"      Issue: {error}")
        if len(results.invalid_name_manifests) > 3:
            click.echo(f"    ... and {len(results.invalid_name_manifests) - 3} more")

    # Old format manifests
    if results.old_format_manifests:
        click.echo(
            f"\n  Old Manifest Format ({len(results.old_format_manifests)} manifest{'s' if len(results.old_format_manifests) > 1 else ''}):"
        )
        click.echo("  These manifests use deprecated 'target' field instead of 'destination'.")
        for manifest_path in results.old_format_manifests[:3]:
            click.echo(f"    • {manifest_path}")
        if len(results.old_format_manifests) > 3:
            click.echo(f"    ... and {len(results.old_format_manifests) - 3} more")

    if results.missing_manifests:
        click.echo(
            f"\n  Missing Manifests ({len(results.missing_manifests)} image{'s' if len(results.missing_manifests) > 1 else ''}):"
        )
        click.echo("  These CEFS images have no accompanying manifest file.")
        for manifest_path in results.missing_manifests[:3]:
            click.echo(f"    • {manifest_path}")
        if len(results.missing_manifests) > 3:
            click.echo(f"    ... and {len(results.missing_manifests) - 3} more")

    if results.other_invalid_manifests:
        click.echo(
            f"\n  Other Validation Errors ({len(results.other_invalid_manifests)} manifest{'s' if len(results.other_invalid_manifests) > 1 else ''}):"
        )
        for manifest_path, error in results.other_invalid_manifests[:3]:
            if "Invalid manifest:" in error:
                error = error.split("Invalid manifest:")[-1].strip()
            click.echo(f"    • {manifest_path}")
            click.echo(f"      Issue: {error}")
        if len(results.other_invalid_manifests) > 3:
            click.echo(f"    ... and {len(results.other_invalid_manifests) - 3} more")

    if results.unreadable_manifests:
        click.echo(
            f"\n  Unreadable Manifests ({len(results.unreadable_manifests)} file{'s' if len(results.unreadable_manifests) > 1 else ''}):"
        )
        click.echo("  These manifest files could not be read (corrupt or invalid YAML).")
        for manifest_path, error in results.unreadable_manifests[:3]:
            click.echo(f"    • {manifest_path}")
            if verbose:
                click.echo(f"      Error: {error}")
        if len(results.unreadable_manifests) > 3:
            click.echo(f"    ... and {len(results.unreadable_manifests) - 3} more")

    if results.inprogress_files:
        click.echo(
            f"\n  In-Progress Files ({len(results.inprogress_files)} file{'s' if len(results.inprogress_files) > 1 else ''}):"
        )
        click.echo("  These .inprogress files indicate incomplete operations.")
        for file_with_age in results.inprogress_files[:3]:
            age_str = humanfriendly.format_timespan(file_with_age.age_seconds)
            click.echo(f"    • {file_with_age.path} (age: {age_str})")
        if len(results.inprogress_files) > 3:
            click.echo(f"    ... and {len(results.inprogress_files) - 3} more")

    if results.pending_backups or results.pending_deletes:
        click.echo(
            f"\n  Pending Cleanup ({len(results.pending_backups) + len(results.pending_deletes)} item{'s' if len(results.pending_backups) + len(results.pending_deletes) > 1 else ''}):"
        )
        if results.pending_backups:
            click.echo(f"  .bak items ({len(results.pending_backups)}):")
            for item in results.pending_backups[:2]:
                click.echo(format_cleanup_item(item))
            if len(results.pending_backups) > 2:
                click.echo(f"    ... and {len(results.pending_backups) - 2} more")
        if results.pending_deletes:
            click.echo(f"  .DELETE_ME items ({len(results.pending_deletes)}):")
            for item in results.pending_deletes[:2]:
                click.echo(format_cleanup_item(item))
            if len(results.pending_deletes) > 2:
                click.echo(f"    ... and {len(results.pending_deletes) - 2} more")

    click.echo("\n💡 Recommendations:")

    if results.invalid_name_manifests or results.old_format_manifests:
        click.echo("  • WARNING: These consolidated images contain active compilers but have broken manifests")
        click.echo("  • Items in these images CANNOT be included in reconsolidation operations")
        click.echo("  • To recover these items:")
        click.echo("    1. Identify which compilers are affected (check symlinks pointing to these images)")
        click.echo("    2. Consider re-installing affected compilers to create proper manifests")
        click.echo("    3. Once reinstalled, the old broken images can be garbage collected")
        click.echo("  • Until fixed, these compilers work normally but cannot be reconsolidated")

    if results.missing_manifests:
        click.echo("  • Images without manifests cannot be reconsolidated")
        click.echo("  • Consider identifying and removing obsolete images")

    if results.inprogress_files:
        click.echo("  • In-progress files indicate operations that didn't complete")
        click.echo("  • Review these files to determine if operations should be retried")
        click.echo("  • Safe to remove .inprogress files older than 24 hours")

    if results.pending_backups or results.pending_deletes:
        click.echo("  • Pending cleanup items can be safely removed to free disk space")
        click.echo("  • .bak items: remnants from CEFS conversions (can be directories or symlinks)")
        click.echo("  • .DELETE_ME items: marked for deletion by previous operations")
        click.echo("  • These require manual cleanup (e.g., rm -rf *.bak *.DELETE_ME_*)")
        click.echo("  • Note: 'ce cefs gc' only removes unreferenced CEFS images, not these items")

    if not verbose:
        click.echo("\n📝 Run with --verbose for detailed file-by-file output")


@cefs.command()
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Show detailed information for each check",
)
@click.pass_obj
def fsck(
    context: CliContext,
    verbose: bool,
) -> None:
    """Check CEFS filesystem integrity.

    Validates:
    - Manifest format and content validity
    - Symlink targets exist and point to correct locations
    - Installable names are properly formatted
    - No broken manifest formats (e.g., old 'target' field)
    - In-progress files indicating incomplete operations
    - Pending cleanup tasks (.bak, .DELETE_ME directories)
    """
    state = CEFSState(
        nfs_dir=context.installation_context.destination,
        cefs_image_dir=context.config.cefs.image_dir,
        mount_point=context.config.cefs.mount_point,
    )
    state.scan_cefs_images_with_manifests()

    if verbose:
        click.echo("\n🔍 Scanning CEFS images and validating manifests...")

    results = run_fsck_validation(
        state,
        context.config.cefs.mount_point,
    )

    if verbose:
        display_verbose_fsck_logs(
            state,
            results,
        )

    display_fsck_results(results, verbose)

    # Exit with appropriate code
    if results.has_issues:
        sys.exit(1)
