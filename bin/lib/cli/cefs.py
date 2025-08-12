#!/usr/bin/env python3
"""CEFS (Compiler Explorer FileSystem) v2 commands."""

import hashlib
import logging
import shutil
import tempfile
from pathlib import Path
from typing import List

import click

from lib.ce_install import CliContext, cli
from lib.installable.installable import Installable

_LOGGER = logging.getLogger(__name__)


def calculate_squashfs_hash(squashfs_path: Path) -> str:
    """Calculate SHA256 hash of squashfs image using Python hashlib."""
    sha256_hash = hashlib.sha256()
    with open(squashfs_path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            sha256_hash.update(chunk)
    return sha256_hash.hexdigest()


def detect_nfs_state(nfs_path: Path) -> str:
    """Detect current state: 'symlink', 'directory', or 'missing'."""
    if nfs_path.is_symlink():
        return "symlink"
    elif nfs_path.exists():
        return "directory"
    else:
        return "missing"


def copy_to_cefs_atomically(source_path: Path, cefs_image_path: Path) -> None:
    """Copy a file to CEFS images directory using atomic rename.

    Creates a uniquely named temp file and atomically renames it to ensure
    we never have truncated .img files in the CEFS directory.

    Args:
        source_path: Source squashfs image to copy
        cefs_image_path: Target path in CEFS images directory

    Raises:
        Exception: If copy fails (temp file is cleaned up)
    """
    _LOGGER.info("Copying %s to %s", source_path, cefs_image_path)
    cefs_image_path.parent.mkdir(parents=True, exist_ok=True)

    # Create uniquely named temp file in same directory for atomic rename
    with tempfile.NamedTemporaryFile(
        dir=cefs_image_path.parent, suffix=".tmp", prefix="cefs_", delete=False
    ) as temp_file:
        temp_path = Path(temp_file.name)

        # Copy to temp file
        with open(source_path, "rb") as source_file:
            shutil.copyfileobj(source_file, temp_file, length=1024 * 1024)

    try:
        # Atomic rename - only complete files get .img extension
        temp_path.replace(cefs_image_path)
    except Exception:
        # Clean up temp file on any failure
        temp_path.unlink(missing_ok=True)
        raise


def backup_and_symlink(nfs_path: Path, cefs_target: Path, dry_run: bool) -> None:
    """Backup NFS directory and create CEFS symlink with rollback on failure."""
    backup_path = nfs_path.with_suffix(".bak")

    if dry_run:
        _LOGGER.info("Would backup %s to %s", nfs_path, backup_path)
        _LOGGER.info("Would create symlink %s -> %s", nfs_path, cefs_target)
        return

    try:
        # Remove old backup if it exists
        if backup_path.exists():
            if backup_path.is_dir():
                shutil.rmtree(backup_path)
            else:
                backup_path.unlink()

        # Backup current directory
        nfs_path.rename(backup_path)
        _LOGGER.info("Backed up %s to %s", nfs_path, backup_path)

        # Create symlink
        nfs_path.symlink_to(cefs_target)
        _LOGGER.info("Created symlink %s -> %s", nfs_path, cefs_target)

    except Exception as e:
        # Rollback on failure
        if backup_path.exists():
            nfs_path.unlink(missing_ok=True)
            backup_path.rename(nfs_path)
            _LOGGER.error("Rollback: restored %s from backup", nfs_path)
        raise RuntimeError(f"Failed to create symlink: {e}") from e


def convert_to_cefs(context: CliContext, installable: Installable, force: bool) -> bool:
    """Convert a single installable from squashfs to CEFS.

    Returns True if conversion was successful or already converted.
    """
    # Get paths
    squashfs_image_path = context.config.squashfs.image_dir / f"{installable.install_path}.img"
    nfs_path = context.installation_context.destination / installable.install_path

    # Check if squashfs image exists
    if not squashfs_image_path.exists():
        _LOGGER.error("No squashfs image found for %s at %s", installable.name, squashfs_image_path)
        return False

    # Detect current NFS state
    nfs_state = detect_nfs_state(nfs_path)

    if nfs_state == "symlink":
        if not force:
            _LOGGER.info("Already converted to CEFS: %s", installable.name)
            return True
        _LOGGER.info("Forcing reconversion of already converted: %s", installable.name)

    if nfs_state == "missing":
        _LOGGER.error("NFS directory missing for %s: %s", installable.name, nfs_path)
        return False

    # Calculate hash and set up CEFS paths
    try:
        _LOGGER.info("Calculating hash for %s...", squashfs_image_path)
        hash_value = calculate_squashfs_hash(squashfs_image_path)
        _LOGGER.info("Hash: %s", hash_value)
    except Exception as e:
        _LOGGER.error("Failed to calculate hash for %s: %s", installable.name, e)
        return False

    cefs_image_path = context.config.cefs.image_dir / f"{hash_value}.img"
    cefs_target = Path(f"/cefs/{hash_value}")

    # Copy squashfs to CEFS images directory if not already there
    # Never overwrite - hash ensures content is identical
    if not cefs_image_path.exists():
        if context.installation_context.dry_run:
            _LOGGER.info("Would copy %s to %s", squashfs_image_path, cefs_image_path)
        else:
            try:
                copy_to_cefs_atomically(squashfs_image_path, cefs_image_path)
            except Exception as e:
                _LOGGER.error("Failed to copy image for %s: %s", installable.name, e)
                return False
    else:
        _LOGGER.info("CEFS image already exists: %s", cefs_image_path)

    # Backup NFS directory and create symlink
    try:
        backup_and_symlink(nfs_path, cefs_target, context.installation_context.dry_run)
    except Exception as e:
        _LOGGER.error("Failed to create symlink for %s: %s", installable.name, e)
        return False

    # Post-migration validation (skip in dry-run)
    if not context.installation_context.dry_run:
        if not nfs_path.is_symlink():
            _LOGGER.error("Post-migration check failed: %s is not a symlink", nfs_path)
            return False

        # Check if installable still reports as installed
        if not installable.is_installed():
            _LOGGER.warning("Post-migration check: %s reports not installed", installable.name)
        else:
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
