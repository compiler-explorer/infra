#!/usr/bin/env python3
"""CEFS (Compiler Explorer FileSystem) v2 utility functions."""

import hashlib
import logging
import shutil
import tempfile
from pathlib import Path

_LOGGER = logging.getLogger(__name__)


def get_cefs_image_path(image_dir: Path, hash_value: str) -> Path:
    """Get the full CEFS image path for a given hash.

    Args:
        image_dir: Base image directory (e.g., Path("/efs/cefs-images"))
        hash_value: SHA256 hash string

    Returns:
        Full path to the CEFS image file (e.g., /efs/cefs-images/a1/a1b2c3d4....sqfs)
    """
    subdir = hash_value[:2]
    return image_dir / subdir / f"{hash_value}.sqfs"


def get_cefs_mount_path(mount_point: Path, hash_value: str) -> Path:
    """Get the full CEFS mount target path for a given hash.

    Args:
        mount_point: Base mount point (e.g., Path("/cefs"))
        hash_value: SHA256 hash string

    Returns:
        Full path to the CEFS mount target (e.g., /cefs/a1/a1b2c3d4...)
    """
    subdir = hash_value[:2]
    return mount_point / subdir / hash_value


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

    # Create uniquely named temp file in same directory for atomic rename
    with tempfile.NamedTemporaryFile(
        dir=cefs_image_path.parent, suffix=".tmp", prefix="cefs_", delete=False
    ) as temp_file:
        temp_path = Path(temp_file.name)
        with open(source_path, "rb") as source_file:
            shutil.copyfileobj(source_file, temp_file, length=1024 * 1024)
    try:
        # Atomic rename - only complete files get .sqfs extension
        temp_path.replace(cefs_image_path)
    except Exception:
        # Clean up temp file on any failure
        temp_path.unlink(missing_ok=True)
        raise


def backup_and_symlink(nfs_path: Path, cefs_target: Path, dry_run: bool) -> None:
    """Backup NFS directory and create CEFS symlink with rollback on failure."""
    backup_path = nfs_path.with_name(nfs_path.name + ".bak")

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

        # Backup current directory if it exists
        if nfs_path.exists():
            nfs_path.rename(backup_path)
            _LOGGER.info("Backed up %s to %s", nfs_path, backup_path)

        # Create symlink
        nfs_path.symlink_to(cefs_target)
        _LOGGER.info("Created symlink %s -> %s", nfs_path, cefs_target)

    except OSError as e:
        # Rollback on failure
        if backup_path.exists():
            nfs_path.unlink(missing_ok=True)
            backup_path.rename(nfs_path)
            _LOGGER.error("Rollback: restored %s from backup", nfs_path)
        raise RuntimeError(f"Failed to create symlink: {e}") from e
