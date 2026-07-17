#!/usr/bin/env python3
"""Legacy squashfs to CEFS conversion."""

from __future__ import annotations

import logging
from pathlib import Path

from lib.cefs.deployment import backup_and_symlink, deploy_to_cefs_transactional
from lib.cefs.paths import (
    detect_nfs_state,
    get_cefs_filename_for_image,
    get_cefs_paths,
)
from lib.cefs_manifest import create_installable_manifest_entry, create_manifest

_LOGGER = logging.getLogger(__name__)


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
