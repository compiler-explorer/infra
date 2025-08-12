#!/usr/bin/env python3
"""CEFS (Compiler Explorer FileSystem) v2 commands."""

import logging
from pathlib import Path
from typing import List

import click

from lib.ce_install import CliContext, cli
from lib.cefs import backup_and_symlink, calculate_squashfs_hash, copy_to_cefs_atomically, detect_nfs_state
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

    cefs_image_path = context.config.cefs.image_dir / f"{hash_value}.sqfs"
    cefs_target = Path(f"/cefs/{hash_value}")

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
    if not context.config.cefs.enabled:
        _LOGGER.error("CEFS is disabled in configuration")
        return

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
