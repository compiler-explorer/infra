#!/usr/bin/env python3
"""CEFS path manipulation and filesystem utilities."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

from lib.cefs.constants import NFS_MAX_RECURSION_DEPTH  # noqa: F401 (used in docstring)
from lib.cefs_manifest import generate_cefs_filename

_LOGGER = logging.getLogger(__name__)


class FileWithAge(NamedTuple):
    """File path with age information."""

    path: Path
    age_seconds: float


@dataclass(frozen=True)
class CEFSPaths:
    """Container for CEFS image path and mount path."""

    image_path: Path
    mount_path: Path


def get_cefs_image_path(image_dir: Path, filename: str) -> Path:
    """Get the full CEFS image path for a given filename.

    Args:
        image_dir: Base image directory (e.g., Path("/efs/cefs-images"))
        filename: Complete filename with descriptive suffix

    Returns:
        Full path to the CEFS image file (e.g., /efs/cefs-images/a1/a1b2c3d4....sqfs)
    """
    return image_dir / filename[:2] / filename


def get_cefs_mount_path(mount_point: Path, filename: str) -> Path:
    """Get the full CEFS mount target path for a given hash.

    Args:
        mount_point: Base mount point (e.g., Path("/cefs"))
        filename: Complete filename with descriptive suffix

    Returns:
        Full path to the CEFS mount target (e.g., {mount_point}/a1/a1b2c3d4...)
    """
    return mount_point / filename[:2] / Path(filename).with_suffix("")


def get_cefs_paths(image_dir: Path, mount_point: Path, filename: str) -> CEFSPaths:
    """Get both CEFS image path and mount path for a given filename.

    Args:
        image_dir: Base image directory (e.g., Path("/efs/cefs-images"))
        mount_point: Base mount point (e.g., Path("/cefs"))
        filename: Complete filename with descriptive suffix

    Returns:
        CEFSPaths containing both image_path and mount_path
    """
    return CEFSPaths(
        image_path=get_cefs_image_path(image_dir, filename),
        mount_path=get_cefs_mount_path(mount_point, filename),
    )


def calculate_squashfs_hash(squashfs_path: Path) -> str:
    """Calculate SHA256 hash of squashfs image using Python hashlib."""
    sha256_hash = hashlib.sha256()
    file_size = squashfs_path.stat().st_size
    _LOGGER.debug("Calculating hash for %s (size: %d bytes)", squashfs_path, file_size)
    with open(squashfs_path, "rb") as f:
        for chunk in iter(lambda: f.read(16 * 1024 * 1024), b""):
            sha256_hash.update(chunk)
    full_hash = sha256_hash.hexdigest()
    truncated_hash = full_hash[:24]
    _LOGGER.debug("Hash for %s: full=%s, truncated=%s", squashfs_path, full_hash, truncated_hash)
    return truncated_hash


def get_cefs_filename_for_image(squashfs_path: Path, operation: str, path: Path | None = None) -> str:
    """Generate CEFS filename by calculating hash and adding suffix.

    Combines hash calculation and filename generation into a single operation.

    Args:
        squashfs_path: Path to squashfs image to hash
        operation: Operation type ("install", "convert", "consolidate")
        path: Optional path for suffix generation

    Returns:
        Generated filename with hash and descriptive suffix

    Raises:
        OSError: If unable to read the squashfs file
    """
    hash_value = calculate_squashfs_hash(squashfs_path)
    return generate_cefs_filename(hash_value, operation, path)


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


def parse_cefs_target(cefs_target: Path, cefs_image_dir: Path, mount_point: Path) -> tuple[Path, bool]:
    """Parse CEFS symlink target and return image path and consolidation status.

    Args:
        cefs_target: The symlink target (e.g., {mount_point}/XX/HASH or {mount_point}/XX/HASH/subdir)
        cefs_image_dir: Base directory for CEFS images (e.g., /efs/cefs-images)
        mount_point: CEFS mount point (e.g., /cefs)

    Returns:
        Tuple of (cefs_image_path, is_already_consolidated)

    Raises:
        ValueError: If the CEFS target format is invalid

    Examples:
        >>> parse_cefs_target(Path("/cefs/9d/9da642f654bc890a12345678"), Path("/efs/cefs-images"), Path("/cefs"))
        (Path("/efs/cefs-images/9d/9da642f654bc890a12345678_gcc.sqfs"), False)

        >>> parse_cefs_target(Path("/cefs/ab/abcdef1234567890abcdef12/gcc-4.5"), Path("/efs/cefs-images"), Path("/cefs"))
        (Path("/efs/cefs-images/ab/abcdef1234567890abcdef12_consolidated.sqfs"), True)
    """
    parts = cefs_target.parts
    mount_parts = mount_point.parts
    # Expected: mount_point parts + ('XX', 'HASH', ...) for {mount_point}/XX/HASH/...

    # Check that target starts with mount_point
    if len(parts) < len(mount_parts) + 2:  # Need at least mount_point + XX + HASH
        raise ValueError(f"Invalid CEFS target format: {cefs_target}")

    # Verify the target starts with the mount point
    if parts[: len(mount_parts)] != mount_parts:
        raise ValueError(f"CEFS target must start with {mount_point}: {cefs_target}")

    # Get XX and HASH parts after the mount point
    hash_prefix = parts[len(mount_parts)]  # XX
    hash = parts[len(mount_parts) + 1]  # 24-char hash

    image_dir_subdir = cefs_image_dir / hash_prefix
    matching_files = list(image_dir_subdir.glob(f"{hash}*.sqfs"))

    if not matching_files:
        raise ValueError(f"No CEFS image found for hash {hash} in {image_dir_subdir}")

    cefs_image_path = matching_files[0]

    # If there are more parts after the hash, it's already consolidated
    is_already_consolidated = len(parts) > len(mount_parts) + 2

    return cefs_image_path, is_already_consolidated


def get_extraction_path_from_symlink(symlink_target: Path, mount_point: Path) -> Path | None:
    """Determine what to extract from a CEFS image based on symlink target.

    Returns the relative path after {mount_point}/XX/HASH/ or None if at root.

    Args:
        symlink_target: The symlink target path
        mount_point: CEFS mount point (e.g., /cefs)

    Examples (assuming mount_point=/cefs):
        /cefs/ab/abcd1234567890abcdef12/content → Path("content")
        /cefs/ab/abcd1234567890abcdef12 → None
        /cefs/ab/abcd1234567890abcdef12/gcc-4.5 → Path("gcc-4.5")
        /cefs/ab/abcd1234567890abcdef12/libs/boost → Path("libs/boost")
    """
    parts = symlink_target.parts
    mount_parts = mount_point.parts
    # Need at least mount_point + XX + HASH to have any relative path
    if len(parts) <= len(mount_parts) + 2:
        return None

    relative_parts = parts[len(mount_parts) + 2 :]
    return Path(*relative_parts)


def describe_cefs_image(filename: str, cefs_mount_point: Path) -> list[str]:
    """Get top-level entries from a CEFS image by triggering autofs mount.

    Args:
        filename: The CEFS hash filename to describe
        cefs_mount_point: Base CEFS mount point

    Returns:
        List of top-level entry names in the CEFS image
    """
    cefs_path = get_cefs_mount_path(cefs_mount_point, filename)
    try:
        entries = list(cefs_path.iterdir())
        return sorted([entry.name for entry in entries])
    except OSError:
        return []


def get_current_symlink_targets(path: Path) -> list[Path]:
    """Get symlink targets for a path and its .bak backup if they exist.

    During CEFS operations, directories are moved to .bak before creating symlinks.
    Both the main path and backup could reference CEFS images, especially after
    re-conversions or with deferred cleanup.

    Args:
        path: The path to check

    Returns:
        List of symlink targets (empty if no symlinks exist)
    """
    targets = []
    for p in [path, path.with_name(path.name + ".bak")]:
        if p.is_symlink():
            try:
                targets.append(p.readlink())
            except OSError:
                pass
    return targets


def generate_glob_patterns(pattern: str, max_depth: int | None = None) -> list[str]:
    """Generate glob patterns for depth-limited searching.

    Args:
        pattern: The base pattern to search for (e.g., "*.bak", "*")
        max_depth: Maximum directory depth (0-based). None for unlimited.

    Returns:
        List of glob patterns to use, from shallow to deep

    Examples:
        >>> generate_glob_patterns("*.bak", max_depth=2)
        ["*.bak", "*/*.bak", "*/*/*.bak"]

        >>> generate_glob_patterns("*", max_depth=1)
        ["*", "*/*"]

        >>> generate_glob_patterns("*.yaml", max_depth=None)
        ["**/*.yaml"]
    """
    if max_depth is None:
        return [f"**/{pattern}"]

    return [pattern if depth == 0 else "/".join(["*"] * depth) + "/" + pattern for depth in range(max_depth + 1)]


def glob_with_depth(base_dir: Path, pattern: str, max_depth: int | None = None):
    """Generate paths matching pattern with optional depth limit.

    Combines pattern generation and globbing into a single generator.

    Args:
        base_dir: Directory to search in
        pattern: Glob pattern to match (e.g., "*.bak", "*")
        max_depth: Maximum directory depth (0-based). None for unlimited.
                  Use NFS_MAX_RECURSION_DEPTH for NFS directories.

    Yields:
        Path objects matching the pattern

    Examples:
        >>> list(glob_with_depth(Path("/tmp"), "*.txt", max_depth=1))
        [Path("/tmp/file.txt"), Path("/tmp/subdir/other.txt")]
    """
    patterns = generate_glob_patterns(pattern, max_depth)
    for glob_pattern in patterns:
        yield from base_dir.glob(glob_pattern)
