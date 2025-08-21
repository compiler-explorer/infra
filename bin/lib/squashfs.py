#!/usr/bin/env python3
"""Utilities for working with squashfs images."""

from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class SquashfsEntry:
    """Represents a parsed entry from unsquashfs -ll output."""

    file_type: str  # 'd', 'l', '-', 'c', 'b', etc.
    size: int  # File size in bytes (0 for non-regular files)
    path: str  # Relative path without leading slash
    target: str | None = None  # Target for symlinks


def parse_unsquashfs_line(line: str) -> SquashfsEntry | None:
    """Parse a single line from unsquashfs -ll output.

    Returns SquashfsEntry with parsed data, or None for intentionally skipped entries (root dir).
    Raises ValueError for unparseable lines.
    """
    pattern = re.compile(
        r"^(?P<permissions>[dlcbps-][rwxst-]{9})\s+"
        r"(?P<owner_group>\S+)\s+"
        r"(?P<size>\d+)\s+"
        r"(?P<date>\d{4}-\d{2}-\d{2})\s+"
        r"(?P<time>\d{2}:\d{2})"
        r"(?:\s+(?P<path_part>.+?))?\s*"  # Allow trailing whitespace
        r"$"
    )

    stripped_line = line.strip()
    if not stripped_line:
        return None  # Empty lines are ok to skip

    match = pattern.match(stripped_line)
    if not match:
        raise ValueError(f"Cannot parse unsquashfs line: {line}")

    groups = match.groupdict()

    # No path means root directory - skip it
    if not groups["path_part"]:
        return None

    file_type = groups["permissions"][0]

    # Handle symlinks: "path -> target"
    # Only split on ' -> ' if this is actually a symlink (type 'l')
    target = None
    path_part = groups["path_part"]
    if file_type == "l" and " -> " in path_part:
        path, target = path_part.split(" -> ", 1)
    else:
        path = path_part

    # Remove leading slash for relative comparison
    if path.startswith("/"):
        path = path[1:]

    if not path:  # Skip empty paths
        return None

    return SquashfsEntry(
        file_type=file_type,
        size=int(groups["size"]) if file_type == "-" else 0,
        path=path,
        target=target if target else None,
    )


def verify_squashfs_contents(img_path: Path, nfs_path: Path) -> int:
    """Verify squashfs image contents match NFS directory. Returns error count."""
    error_count = 0

    try:
        # Extract squashfs metadata without mounting
        result = subprocess.run(
            ["unsquashfs", "-ll", "-d", "", str(img_path)], capture_output=True, text=True, check=True
        )
        sqfs_output = result.stdout
    except subprocess.CalledProcessError as e:
        _LOGGER.error("Failed to read squashfs image %s: %s", img_path, e)
        return 1
    except FileNotFoundError:
        _LOGGER.error("unsquashfs command not found - install squashfs-tools")
        return 1

    # Parse squashfs output to get file list
    sqfs_files: dict[str, tuple[str, str]] = {}
    for line in sqfs_output.split("\n"):
        if not line.strip():
            continue

        # Skip known header lines from unsquashfs
        if line.startswith("Parallel unsquashfs:") or line.startswith("Filesystem on"):
            continue

        try:
            parsed = parse_unsquashfs_line(line)
            if parsed is None:
                # None means intentionally skipped (e.g., root directory, empty lines)
                continue
            sqfs_files[parsed.path] = (parsed.file_type, str(parsed.size))
        except ValueError as e:
            _LOGGER.error("Failed to parse unsquashfs output: %s", e)
            raise

    # Build equivalent from directory filesystem
    dir_files: dict[str, tuple[str, str]] = {}
    if not nfs_path.exists():
        _LOGGER.error("Directory does not exist: %s", nfs_path)
        return 1

    for item in nfs_path.rglob("*"):
        rel_path = str(item.relative_to(nfs_path))

        stat_result = item.lstat()

        if item.is_symlink():
            file_type = "l"
            size = "0"
        elif item.is_dir():
            file_type = "d"
            size = "0"
        elif item.is_file():
            file_type = "-"
            size = str(stat_result.st_size)
        else:
            raise ValueError(f"Unknown file type for {item}")

        dir_files[rel_path] = (file_type, size)

    # Compare file sets
    only_in_sqfs = set(sqfs_files.keys()) - set(dir_files.keys())
    only_in_dir = set(dir_files.keys()) - set(sqfs_files.keys())

    # Report files only in one location
    if only_in_sqfs:
        error_count += len(only_in_sqfs)
        _LOGGER.error(
            "Files only in squashfs (%d): %s",
            len(only_in_sqfs),
            ", ".join(sorted(list(only_in_sqfs)[:5])) + ("..." if len(only_in_sqfs) > 5 else ""),
        )

    if only_in_dir:
        error_count += len(only_in_dir)
        _LOGGER.error(
            "Files only in directory (%d): %s",
            len(only_in_dir),
            ", ".join(sorted(list(only_in_dir)[:5])) + ("..." if len(only_in_dir) > 5 else ""),
        )

    # Check common files for mismatches
    mismatches = 0
    for path in set(sqfs_files.keys()) & set(dir_files.keys()):
        sqfs_meta = sqfs_files[path]
        dir_meta = dir_files[path]

        # Compare type and size
        if sqfs_meta[0] != dir_meta[0]:
            _LOGGER.error("Type mismatch for %s: squashfs=%s, directory=%s", path, sqfs_meta[0], dir_meta[0])
            mismatches += 1
        elif sqfs_meta[0] == "-" and sqfs_meta[1] != dir_meta[1]:
            _LOGGER.error("Size mismatch for %s: squashfs=%s, directory=%s", path, sqfs_meta[1], dir_meta[1])
            mismatches += 1

    error_count += mismatches

    # Debug info
    _LOGGER.info("Found %d files in squashfs, %d files in directory", len(sqfs_files), len(dir_files))

    if error_count == 0:
        _LOGGER.info("✓ Contents match: %d files verified", len(sqfs_files))
    else:
        _LOGGER.error("✗ Contents mismatch: %d errors found", error_count)

    return error_count


def create_squashfs_image(
    config_squashfs,
    source_path: Path,
    output_path: Path,
    compression: str | None = None,
    compression_level: int | None = None,
    additional_args: list[str] | None = None,
) -> None:
    """Create a squashfs image using configured mksquashfs tool.

    Args:
        config_squashfs: SquashFsConfig object with tool paths and settings
        source_path: Source directory to compress
        output_path: Output squashfs file path
        compression: Compression type (defaults to config.compression)
        compression_level: Compression level (defaults to config.compression_level)
        additional_args: Additional arguments to pass to mksquashfs

    Raises:
        subprocess.CalledProcessError: If mksquashfs command fails
    """
    cmd = [
        config_squashfs.mksquashfs_path,
        str(source_path),
        str(output_path),
        "-all-root",
        "-progress",
        "-comp",
        compression or config_squashfs.compression,
        "-Xcompression-level",
        str(compression_level or config_squashfs.compression_level),
        "-noappend",  # Don't append, create new
    ]

    if additional_args:
        cmd.extend(additional_args)

    subprocess.run(cmd, check=True, capture_output=True, text=True)


def extract_squashfs_image(
    config_squashfs,
    squashfs_path: Path,
    output_dir: Path,
    extract_path: Path | None = None,
) -> None:
    """Extract a squashfs image using configured unsquashfs tool.

    Args:
        config_squashfs: SquashFsConfig object with tool paths
        squashfs_path: Path to squashfs file to extract
        output_dir: Directory to extract to
        extract_path: Specific path within the archive to extract (optional)

    Raises:
        subprocess.CalledProcessError: If unsquashfs command fails
    """
    cmd = [
        config_squashfs.unsquashfs_path,
        "-f",  # Force overwrite
        "-d",
        str(output_dir),  # Destination directory
        str(squashfs_path),
    ]

    if extract_path and extract_path != Path("."):
        cmd.append(str(extract_path))  # Extract this specific path

    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise subprocess.CalledProcessError(result.returncode, cmd, output=result.stdout, stderr=result.stderr)
