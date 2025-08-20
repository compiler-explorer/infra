#!/usr/bin/env python3
"""CEFS (Compiler Explorer FileSystem) v2 utility functions."""

from __future__ import annotations

import hashlib
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import humanfriendly

_LOGGER = logging.getLogger(__name__)


def get_cefs_image_path(image_dir: Path, hash: str, filename: str) -> Path:
    """Get the full CEFS image path for a given hash and filename.

    Args:
        image_dir: Base image directory (e.g., Path("/efs/cefs-images"))
        hash: 24-character hash
        filename: Complete filename with descriptive suffix

    Returns:
        Full path to the CEFS image file (e.g., /efs/cefs-images/a1/a1b2c3d4....sqfs)
    """
    subdir = hash[:2]
    return image_dir / subdir / filename


def get_cefs_mount_path(mount_point: Path, hash: str) -> Path:
    """Get the full CEFS mount target path for a given hash.

    Args:
        mount_point: Base mount point (e.g., Path("/cefs"))
        hash: 24-character hash

    Returns:
        Full path to the CEFS mount target (e.g., /cefs/a1/a1b2c3d4...)
    """
    subdir = hash[:2]
    return mount_point / subdir / hash


def calculate_squashfs_hash(squashfs_path: Path) -> str:
    """Calculate SHA256 hash of squashfs image using Python hashlib."""
    sha256_hash = hashlib.sha256()
    with open(squashfs_path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            sha256_hash.update(chunk)
    return sha256_hash.hexdigest()[:24]


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


def get_directory_size(directory: Path) -> int:
    """Calculate total size of a directory tree in bytes.

    Args:
        directory: Directory to measure

    Returns:
        Total size in bytes
    """
    total_size = 0
    try:
        for item in directory.rglob("*"):
            if item.is_file() and not item.is_symlink():
                total_size += item.stat().st_size
    except OSError as e:
        _LOGGER.warning("Error calculating directory size for %s: %s", directory, e)
    return total_size


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
        return available_bytes >= required_bytes
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


def create_consolidated_image(
    items: list[tuple[Path, Path, str, Path]],
    temp_dir: Path,
    output_path: Path,
    compression: str = "zstd",
    compression_level: int = 7,
) -> None:
    """Create a consolidated squashfs image from multiple CEFS items.

    Args:
        items: List of (nfs_path, squashfs_path, subdirectory_name, extraction_path) tuples
        temp_dir: Temporary directory for extraction
        output_path: Path for the consolidated squashfs image
        compression: Squashfs compression type
        compression_level: Compression level

    Raises:
        RuntimeError: If consolidation fails
    """
    extraction_dir = temp_dir / "extract"
    extraction_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Extract each squashfs image to its subdirectory
        total_compressed_size = 0
        total_extracted_size = 0

        for _nfs_path, squashfs_path, subdir_name, extraction_path in items:
            subdir_path = extraction_dir / subdir_name
            compressed_size = squashfs_path.stat().st_size
            total_compressed_size += compressed_size

            _LOGGER.info(
                "Extracting %s (%s) from %s to %s",
                squashfs_path,
                humanfriendly.format_size(compressed_size, binary=True),
                extraction_path,
                subdir_path,
            )

            cmd = [
                "unsquashfs",
                "-f",  # Force overwrite
                "-d",
                str(subdir_path),  # Destination directory
                str(squashfs_path),
            ]
            if extraction_path != Path("."):
                cmd.append(str(extraction_path))  # Extract this specific path

            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if result.returncode != 0:
                raise RuntimeError(f"Failed to extract {squashfs_path} path {extraction_path}: {result.stderr}")

            # Measure extracted size and calculate compression ratio
            extracted_size = get_directory_size(subdir_path)
            total_extracted_size += extracted_size
            compression_ratio = extracted_size / compressed_size if compressed_size > 0 else 0

            _LOGGER.info(
                "Extracted %s -> %s (%.1fx compression)",
                humanfriendly.format_size(compressed_size, binary=True),
                humanfriendly.format_size(extracted_size, binary=True),
                compression_ratio,
            )

        # Log total extraction summary
        total_compression_ratio = total_extracted_size / total_compressed_size if total_compressed_size > 0 else 0
        _LOGGER.info(
            "Total extraction: %s -> %s (%.1fx compression)",
            humanfriendly.format_size(total_compressed_size, binary=True),
            humanfriendly.format_size(total_extracted_size, binary=True),
            total_compression_ratio,
        )

        # Create consolidated squashfs image
        _LOGGER.info("Creating consolidated squashfs image at %s", output_path)
        cmd = [
            "mksquashfs",
            str(extraction_dir),
            str(output_path),
            "-comp",
            compression,
            "-Xcompression-level",
            str(compression_level),
            "-noappend",  # Don't append, create new
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise RuntimeError(f"Failed to create consolidated squashfs: {result.stderr}")

        # Log final consolidation compression ratio
        consolidated_size = output_path.stat().st_size
        final_compression_ratio = total_extracted_size / consolidated_size if consolidated_size > 0 else 0

        # Calculate space savings vs original and total compression
        space_savings_ratio = total_compressed_size / consolidated_size if consolidated_size > 0 else 0
        total_compression_ratio = total_extracted_size / consolidated_size if consolidated_size > 0 else 0

        _LOGGER.info("Consolidation complete:")
        _LOGGER.info(
            "  Final image: %s (%.1fx compression of extracted data)",
            humanfriendly.format_size(consolidated_size, binary=True),
            final_compression_ratio,
        )
        _LOGGER.info(
            "  Space comparison: %s -> %s (%.1fx space savings)",
            humanfriendly.format_size(total_compressed_size, binary=True),
            humanfriendly.format_size(consolidated_size, binary=True),
            space_savings_ratio,
        )
        _LOGGER.info(
            "  Total compression: %s -> %s (%.1fx overall compression)",
            humanfriendly.format_size(total_extracted_size, binary=True),
            humanfriendly.format_size(consolidated_size, binary=True),
            total_compression_ratio,
        )

    finally:
        # Clean up extraction directory
        if extraction_dir.exists():
            shutil.rmtree(extraction_dir)
            _LOGGER.debug("Cleaned up extraction directory: %s", extraction_dir)


def update_symlinks_for_consolidation(
    unchanged_symlinks: list[Path], consolidated_hash: str, mount_point: Path, subdir_mapping: dict[Path, str]
) -> None:
    """Update symlinks to point to consolidated CEFS mount.

    Args:
        unchanged_symlinks: List of symlinks that are safe to update
        consolidated_hash: Hash of the consolidated image
        mount_point: CEFS mount point
        subdir_mapping: Mapping of nfs_path to subdirectory name in consolidated image

    Raises:
        RuntimeError: If symlink update fails
    """
    for symlink_path in unchanged_symlinks:
        if symlink_path not in subdir_mapping:
            _LOGGER.warning("No subdirectory mapping for %s, skipping", symlink_path)
            continue

        subdir_name = subdir_mapping[symlink_path]
        # New target: /cefs/XX/HASH/subdir_name
        new_target = get_cefs_mount_path(mount_point, consolidated_hash) / subdir_name

        try:
            # Use existing backup_and_symlink function for consistency with convert
            backup_and_symlink(symlink_path, new_target, dry_run=False)
            _LOGGER.info("Updated symlink %s -> %s", symlink_path, new_target)
        except RuntimeError as e:
            raise RuntimeError(f"Failed to update symlink {symlink_path}: {e}") from e


def parse_cefs_target(cefs_target: Path, cefs_image_dir: Path) -> tuple[Path, bool]:
    """Parse CEFS symlink target and return image path and consolidation status.

    Args:
        cefs_target: The symlink target (e.g., /cefs/XX/HASH or /cefs/XX/HASH/subdir)
        cefs_image_dir: Base directory for CEFS images (e.g., /efs/cefs-images)

    Returns:
        Tuple of (cefs_image_path, is_already_consolidated)

    Raises:
        ValueError: If the CEFS target format is invalid

    Examples:
        >>> parse_cefs_target(Path("/cefs/9d/9da642f654bc890a12345678"), Path("/efs/cefs-images"))
        (Path("/efs/cefs-images/9d/9da642f654bc890a12345678_gcc.sqfs"), False)

        >>> parse_cefs_target(Path("/cefs/ab/abcdef1234567890abcdef12/gcc-4.5"), Path("/efs/cefs-images"))
        (Path("/efs/cefs-images/ab/abcdef1234567890abcdef12_consolidated.sqfs"), True)
    """
    parts = cefs_target.parts
    # Expected: ('', 'cefs', 'XX', 'HASH', ...) for /cefs/XX/HASH/...

    if len(parts) < 4:  # Need at least '', 'cefs', 'XX', 'HASH'
        raise ValueError(f"Invalid CEFS target format: {cefs_target}")

    if parts[1] != "cefs":
        raise ValueError(f"CEFS target must start with /cefs: {cefs_target}")

    hash_prefix = parts[2]  # XX
    hash = parts[3]  # 24-char hash

    image_dir_subdir = cefs_image_dir / hash_prefix
    matching_files = list(image_dir_subdir.glob(f"{hash}*.sqfs"))

    if not matching_files:
        raise ValueError(f"No CEFS image found for hash {hash} in {image_dir_subdir}")

    cefs_image_path = matching_files[0]

    # If there are more parts after the hash, it's already consolidated
    is_already_consolidated = len(parts) > 4

    return cefs_image_path, is_already_consolidated


def get_extraction_path_from_symlink(symlink_target: Path) -> Path:
    """Determine what to extract from a CEFS image based on symlink target.

    Returns the relative path after /cefs/XX/HASH/ or Path(".") if at root.

    Examples:
        /cefs/ab/abcd1234567890abcdef12/content → Path("content")
        /cefs/ab/abcd1234567890abcdef12 → Path(".")
        /cefs/ab/abcd1234567890abcdef12/gcc-4.5 → Path("gcc-4.5")
        /cefs/ab/abcd1234567890abcdef12/libs/boost → Path("libs/boost")
    """
    parts = symlink_target.parts
    if len(parts) <= 4:
        return Path(".")

    relative_parts = parts[4:]
    return Path(*relative_parts)
