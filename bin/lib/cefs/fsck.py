#!/usr/bin/env python3
"""CEFS filesystem checking and validation."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from lib.cefs.constants import NFS_MAX_RECURSION_DEPTH
from lib.cefs.paths import FileWithAge
from lib.cefs.state import CEFSState
from lib.cefs_manifest import validate_manifest

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class FSCKResults:
    """Results from CEFS filesystem check."""

    total_images: int = 0
    valid_manifests: int = 0
    missing_manifests: list[Path] = field(default_factory=list)
    old_format_manifests: list[Path] = field(default_factory=list)
    invalid_name_manifests: list[tuple[Path, str]] = field(default_factory=list)
    other_invalid_manifests: list[tuple[Path, str]] = field(default_factory=list)
    unreadable_manifests: list[tuple[Path, str]] = field(default_factory=list)
    inprogress_files: list[FileWithAge] = field(default_factory=list)
    pending_backups: list[FileWithAge] = field(default_factory=list)
    pending_deletes: list[FileWithAge] = field(default_factory=list)

    @property
    def total_invalid(self) -> int:
        """Total number of invalid manifests."""
        return (
            len(self.missing_manifests)
            + len(self.old_format_manifests)
            + len(self.invalid_name_manifests)
            + len(self.other_invalid_manifests)
            + len(self.unreadable_manifests)
        )

    @property
    def has_issues(self) -> bool:
        """Check if any issues were found."""
        return (
            self.total_invalid > 0
            or len(self.inprogress_files) > 0
            or len(self.pending_backups) > 0
            or len(self.pending_deletes) > 0
        )


def find_files_by_pattern(
    base_dir: Path,
    pattern: str,
    current_time: float,
    max_depth: int | None = None,
) -> list[FileWithAge]:
    """Find files matching pattern and return with age.

    Args:
        base_dir: Directory to search
        pattern: Glob pattern (e.g., "*.bak")
        current_time: Current time for age calculation
        max_depth: Maximum directory depth (None for unlimited)

    Returns:
        List of FileWithAge tuples
    """
    # Build list of glob patterns based on max_depth
    if max_depth is None:
        patterns = [f"**/{pattern}"]
    else:
        patterns = [
            pattern if depth == 0 else "/".join(["*"] * depth) + "/" + pattern for depth in range(max_depth + 1)
        ]

    # Single loop to process all patterns
    results = []
    for glob_pattern in patterns:
        for path in base_dir.glob(glob_pattern):
            try:
                # Use lstat to get the modification time of the item itself (not following symlinks)
                mtime = path.lstat().st_mtime
                results.append(FileWithAge(path, current_time - mtime))
            except OSError:
                # File disappeared or permission denied - skip silently
                continue

    return results


def check_inprogress_files(cefs_image_dir: Path, current_time: float) -> list[FileWithAge]:
    """Check for yaml.inprogress files only (no sqfs checks).

    Args:
        cefs_image_dir: Path to CEFS images directory
        current_time: Current time for age calculation

    Returns:
        List of FileWithAge tuples sorted by age (oldest first)
    """
    # CEFS dir uses unlimited depth (it's local, not NFS)
    files = find_files_by_pattern(cefs_image_dir, "*.yaml.inprogress", current_time, max_depth=None)
    # Sort by age (oldest first)
    return sorted(files, key=lambda x: x.age_seconds, reverse=True)


def validate_single_manifest(manifest_path: Path, mount_point: Path, filename_stem: str) -> tuple[bool, str | None]:
    """Validate a single manifest file.

    Args:
        manifest_path: Path to the manifest file
        mount_point: CEFS mount point
        filename_stem: Stem of the image filename

    Returns:
        Tuple of (is_valid, error_type)
        where error_type is None if valid, or one of:
        - "missing": manifest file doesn't exist
        - "unreadable": file exists but can't be read
        - "old_format": uses deprecated 'target' field
        - "invalid_name": has invalid installable names
        - "other": other validation errors
    """
    if not manifest_path.exists():
        return False, "missing"

    try:
        with manifest_path.open(encoding="utf-8") as f:
            manifest_dict = yaml.safe_load(f)
    except (OSError, yaml.YAMLError):
        return False, "unreadable"

    contents = manifest_dict.get("contents", []) if manifest_dict else []

    if any("target" in content for content in contents):
        return False, "old_format"

    try:
        validate_manifest(manifest_dict)
    except ValueError as e:
        error_msg = str(e).lower()
        error_type = (
            "invalid_name" if "invalid name" in error_msg or "entries with invalid name" in error_msg else "other"
        )
        return False, error_type

    return True, None


def run_fsck_validation(
    state: CEFSState,
    mount_point: Path,
) -> FSCKResults:
    """Run CEFS filesystem validation checks.

    Args:
        state: CEFSState with scanned images
        mount_point: CEFS mount point

    Returns:
        FSCKResults containing all validation results
    """
    total_images = 0
    valid_manifests = 0
    missing_manifests = []
    old_format_manifests = []
    invalid_name_manifests = []
    other_invalid_manifests = []
    unreadable_manifests = []

    for filename_stem, image_path in state.all_cefs_images.items():
        total_images += 1
        manifest_path = image_path.with_suffix(".yaml")
        is_valid, error_type = validate_single_manifest(manifest_path, mount_point, filename_stem)

        if is_valid:
            valid_manifests += 1
        else:
            match error_type:
                case "missing":
                    missing_manifests.append(manifest_path)
                case "old_format":
                    old_format_manifests.append(manifest_path)
                case "invalid_name" | "other":
                    # Re-validate to capture the specific error message since we only got the type earlier
                    try:
                        with manifest_path.open(encoding="utf-8") as f:
                            manifest_dict = yaml.safe_load(f)
                        validate_manifest(manifest_dict)
                    except ValueError as e:
                        if error_type == "invalid_name":
                            invalid_name_manifests.append((manifest_path, str(e)))
                        else:
                            other_invalid_manifests.append((manifest_path, str(e)))
                case "unreadable":
                    unreadable_manifests.append((manifest_path, "Cannot read manifest file"))

    current_time = time.time()
    inprogress_files = check_inprogress_files(state.cefs_image_dir, current_time)
    pending_backups = find_files_by_pattern(state.nfs_dir, "*.bak", current_time, max_depth=NFS_MAX_RECURSION_DEPTH)
    pending_deletes = find_files_by_pattern(
        state.nfs_dir, "*.DELETE_ME_*", current_time, max_depth=NFS_MAX_RECURSION_DEPTH
    )

    return FSCKResults(
        total_images=total_images,
        valid_manifests=valid_manifests,
        missing_manifests=missing_manifests,
        old_format_manifests=old_format_manifests,
        invalid_name_manifests=invalid_name_manifests,
        other_invalid_manifests=other_invalid_manifests,
        unreadable_manifests=unreadable_manifests,
        inprogress_files=inprogress_files,
        pending_backups=pending_backups,
        pending_deletes=pending_deletes,
    )
