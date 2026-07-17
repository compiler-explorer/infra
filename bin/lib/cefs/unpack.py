#!/usr/bin/env python3
"""CEFS unpack and repack operations for in-place modifications."""

from __future__ import annotations

import datetime
import logging
import shutil
import uuid
from pathlib import Path

from lib.cefs.deployment import backup_and_symlink, deploy_to_cefs_transactional
from lib.cefs.paths import get_cefs_filename_for_image, get_cefs_paths, parse_cefs_target
from lib.cefs_manifest import create_installable_manifest_entry, create_manifest
from lib.config import SquashfsConfig
from lib.squashfs import create_squashfs_image, extract_squashfs_relocating_subdir

_LOGGER = logging.getLogger(__name__)


def unpack_cefs_item(
    installable_name: str,
    nfs_path: Path,
    cefs_image_dir: Path,
    mount_point: Path,
    squashfs_config: SquashfsConfig,
    defer_cleanup: bool,
    dry_run: bool,
) -> bool:
    """Unpack a CEFS image to a real directory for in-place modifications.

    Extracts the CEFS image and replaces the symlink with the actual directory.
    The original symlink is saved as .bak for rollback.

    Args:
        installable_name: Full installable name (for logging)
        nfs_path: Path to the NFS installation (currently a symlink to CEFS)
        cefs_image_dir: Base directory for CEFS images
        mount_point: CEFS mount point
        squashfs_config: Squashfs configuration for extraction
        defer_cleanup: If True, rename old .bak to .DELETE_ME instead of deleting
        dry_run: If True, only log what would be done

    Returns:
        True if successful, False otherwise

    Raises:
        RuntimeError: If unpacking fails
    """
    # Verify it's a CEFS symlink
    if not nfs_path.is_symlink():
        raise RuntimeError(f"{nfs_path} is not a symlink (already unpacked or not a CEFS installation?)")

    try:
        symlink_target = nfs_path.readlink()
    except OSError as e:
        raise RuntimeError(f"Failed to read symlink {nfs_path}: {e}") from e

    # Parse the CEFS target to find the image
    try:
        cefs_image_path, is_consolidated = parse_cefs_target(symlink_target, cefs_image_dir, mount_point)
    except ValueError as e:
        raise RuntimeError(f"Invalid CEFS symlink target {symlink_target}: {e}") from e

    if not cefs_image_path.exists():
        raise RuntimeError(f"CEFS image not found: {cefs_image_path}")

    _LOGGER.info("Unpacking %s from %s", installable_name, cefs_image_path)
    if is_consolidated:
        _LOGGER.info("This is from a consolidated image, will extract only the needed subdirectory")

    # Determine what to extract
    extraction_path = None
    if is_consolidated:
        # Extract only the subdirectory we need
        # symlink_target format: /cefs/XX/HASH/subdir
        parts = symlink_target.parts
        mount_parts = mount_point.parts
        if len(parts) > len(mount_parts) + 2:
            extraction_path = Path(*parts[len(mount_parts) + 2 :])
            _LOGGER.debug("Will extract subdirectory: %s", extraction_path)

    if dry_run:
        _LOGGER.info("DRY RUN: Would unpack %s to %s", cefs_image_path, nfs_path)
        if extraction_path:
            _LOGGER.info("DRY RUN: Would extract only: %s", extraction_path)
        return True

    # Create temp directory for extraction with unique name
    temp_name = f"{nfs_path.name}.UNPACK_{uuid.uuid4().hex[:8]}"
    temp_path = nfs_path.parent / temp_name

    try:
        # Extract to temp directory
        _LOGGER.info("Extracting to temporary location: %s", temp_path)
        extract_squashfs_relocating_subdir(squashfs_config, cefs_image_path, temp_path, extraction_path)

        backup_path = nfs_path.with_name(nfs_path.name + ".bak")

        # Handle old .bak if it exists
        if backup_path.exists(follow_symlinks=False):
            if defer_cleanup:
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                delete_me_path = nfs_path.with_name(f"{nfs_path.name}.DELETE_ME_{timestamp}")
                backup_path.rename(delete_me_path)
                _LOGGER.info("Renamed old backup %s to %s for deferred cleanup", backup_path, delete_me_path)
            else:
                if backup_path.is_symlink():
                    backup_path.unlink()
                else:
                    shutil.rmtree(backup_path)
                _LOGGER.debug("Removed old backup: %s", backup_path)

        # Atomic rename sequence: symlink → .bak, temp → main
        _LOGGER.info("Replacing symlink with unpacked directory")
        nfs_path.rename(backup_path)
        _LOGGER.debug("Renamed symlink %s to %s", nfs_path, backup_path)

        temp_path.rename(nfs_path)
        _LOGGER.info("Unpacked %s successfully", installable_name)

        return True

    except Exception as e:
        # Clean up temp directory on failure
        if temp_path.exists():
            shutil.rmtree(temp_path)
            _LOGGER.debug("Cleaned up temp directory: %s", temp_path)
        raise RuntimeError(f"Failed to unpack {installable_name}: {e}") from e


def repack_cefs_item(
    installable_name: str,
    nfs_path: Path,
    cefs_image_dir: Path,
    mount_point: Path,
    squashfs_config: SquashfsConfig,
    local_temp_dir: Path,
    defer_cleanup: bool,
    dry_run: bool,
) -> bool:
    """Repack a directory back into a CEFS image.

    Creates a new squashfs image from the unpacked directory and deploys it
    to CEFS with a new hash. The directory is replaced with a symlink.

    Args:
        installable_name: Full installable name
        nfs_path: Path to the NFS installation (currently a directory)
        cefs_image_dir: Base directory for CEFS images
        mount_point: CEFS mount point
        squashfs_config: Squashfs configuration for compression
        local_temp_dir: Temporary directory for creating images
        defer_cleanup: If True, rename old .bak to .DELETE_ME instead of deleting
        dry_run: If True, only log what would be done

    Returns:
        True if successful, False otherwise

    Raises:
        RuntimeError: If repacking fails
    """
    # Verify it's a directory (not a symlink)
    if nfs_path.is_symlink():
        raise RuntimeError(f"{nfs_path} is a symlink (not unpacked, use 'ce install' instead)")

    if not nfs_path.is_dir():
        raise RuntimeError(f"{nfs_path} is not a directory")

    _LOGGER.info("Repacking %s from %s", installable_name, nfs_path)

    if dry_run:
        _LOGGER.info("DRY RUN: Would repack %s to new CEFS image", nfs_path)
        return True

    # Create temp directory for the new squashfs image
    repack_dir = local_temp_dir / f"repack_{uuid.uuid4().hex[:8]}"
    repack_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Create squashfs image from the directory
        temp_image_path = repack_dir / "repacked.sqfs"
        _LOGGER.info("Creating squashfs image from %s", nfs_path)
        create_squashfs_image(squashfs_config, nfs_path, temp_image_path)

        # Generate new filename with hash
        filename = get_cefs_filename_for_image(temp_image_path, "install", nfs_path)
        cefs_paths = get_cefs_paths(cefs_image_dir, mount_point, filename)

        _LOGGER.info("New CEFS image will be: %s", cefs_paths.image_path)

        # Create manifest for the new image
        manifest_entry = create_installable_manifest_entry(installable_name, nfs_path)
        manifest = create_manifest(
            operation="install",
            description=f"Repacked from modified directory: {installable_name}",
            contents=[manifest_entry],
        )

        # Deploy to CEFS
        with deploy_to_cefs_transactional(temp_image_path, cefs_paths.image_path, manifest, dry_run):
            # Replace directory with symlink using backup_and_symlink
            # This handles the backup and rollback for us
            backup_and_symlink(nfs_path, cefs_paths.mount_path, dry_run, defer_cleanup)
            _LOGGER.info("Replaced directory with CEFS symlink")

        _LOGGER.info("Repacked %s successfully to %s", installable_name, cefs_paths.image_path)
        return True

    except Exception as e:
        raise RuntimeError(f"Failed to repack {installable_name}: {e}") from e

    finally:
        # Clean up temp directory
        if repack_dir.exists():
            shutil.rmtree(repack_dir)
            _LOGGER.debug("Cleaned up repack directory: %s", repack_dir)
