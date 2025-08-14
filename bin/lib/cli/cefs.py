#!/usr/bin/env python3
"""CEFS (Compiler Explorer FileSystem) v2 commands."""

import logging
import subprocess
from typing import List

import click

from lib.ce_install import CliContext, cli
from lib.cefs import (
    backup_and_symlink,
    calculate_squashfs_hash,
    copy_to_cefs_atomically,
    detect_nfs_state,
    get_cefs_image_path,
    get_cefs_mount_path,
    validate_cefs_mount_point,
)
from lib.installable.installable import Installable

_LOGGER = logging.getLogger(__name__)


def convert_to_cefs(context: CliContext, installable: Installable, force: bool) -> bool:
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

    # Calculate hash and set up CEFS paths
    try:
        _LOGGER.info("Calculating hash for %s...", squashfs_image_path)
        hash_value = calculate_squashfs_hash(squashfs_image_path)
        _LOGGER.info("Hash: %s", hash_value)
    except RuntimeError as e:
        _LOGGER.error("Failed to calculate hash for %s: %s", installable.name, e)
        return False

    cefs_image_path = get_cefs_image_path(context.config.cefs.image_dir, hash_value)
    cefs_target = get_cefs_mount_path(context.config.cefs.mount_point, hash_value)

    # Copy squashfs to CEFS images directory if not already there
    # Never overwrite - hash ensures content is identical
    if not cefs_image_path.exists():
        if context.installation_context.dry_run:
            _LOGGER.info("Would copy %s to %s", squashfs_image_path, cefs_image_path)
        else:
            try:
                copy_to_cefs_atomically(squashfs_image_path, cefs_image_path)
            except RuntimeError as e:
                _LOGGER.error("Failed to copy image for %s: %s", installable.name, e)
                return False
    else:
        _LOGGER.info("CEFS image already exists: %s", cefs_image_path)

    # Backup NFS directory and create symlink
    try:
        backup_and_symlink(nfs_path, cefs_target, context.installation_context.dry_run)
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
@click.argument("filter_", metavar="FILTER", nargs=-1)
def convert(context: CliContext, filter_: List[str], force: bool):
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
        if convert_to_cefs(context, installable, force):
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
@click.option("--dry-run", is_flag=True, help="Show what would be done without making changes")
@click.argument("filter_", metavar="FILTER", nargs=-1)
def rollback(context: CliContext, filter_: List[str], dry_run: bool):
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

    for installable in installables:
        nfs_path = context.installation_context.destination / installable.install_path
        backup_path = nfs_path.with_suffix(".bak")

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

        if dry_run:
            _LOGGER.info(
                "Would rollback %s: remove symlink %s, restore from %s", installable.name, nfs_path, backup_path
            )
            successful += 1
            continue

        try:
            # Remove symlink
            _LOGGER.info("Removing CEFS symlink: %s", nfs_path)
            nfs_path.unlink()

            # Restore from backup
            _LOGGER.info("Restoring from backup: %s -> %s", backup_path, nfs_path)
            backup_path.rename(nfs_path)

            # Verify restoration
            if installable.is_installed():
                _LOGGER.info("Successfully rolled back %s", installable.name)
                successful += 1
            else:
                _LOGGER.error("Rollback validation failed for %s", installable.name)
                failed += 1

        except OSError as e:
            _LOGGER.error("Failed to rollback %s: %s", installable.name, e)
            failed += 1

    _LOGGER.info("Rollback complete: %d successful, %d failed, %d skipped", successful, failed, skipped)

    if failed > 0:
        raise click.ClickException(f"Failed to rollback {failed} installables")
