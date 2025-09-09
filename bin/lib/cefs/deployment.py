#!/usr/bin/env python3
"""CEFS image deployment and symlink management."""

from __future__ import annotations

import datetime
import logging
import os
import shutil
import tempfile
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from lib.cefs_manifest import finalize_manifest, write_manifest_inprogress

_LOGGER = logging.getLogger(__name__)


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
        # We use symlinks=False here to account for broken symlinks.
        # Handle old backup if it exists
        if backup_path.exists(follow_symlinks=False):
            if defer_cleanup:
                # Rename to .DELETE_ME_<timestamp> for later cleanup
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                delete_me_path = nfs_path.with_name(f"{nfs_path.name}.DELETE_ME_{timestamp}")
                backup_path.rename(delete_me_path)
                _LOGGER.info("Renamed old backup %s to %s for deferred cleanup", backup_path, delete_me_path)
            else:
                # Original behavior: delete immediately
                if backup_path.is_symlink():
                    backup_path.unlink()
                else:
                    shutil.rmtree(backup_path)

        # Backup current directory (or symlink) if it exists.
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
