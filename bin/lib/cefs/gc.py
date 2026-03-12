#!/usr/bin/env python3
"""CEFS garbage collection and cleanup."""

from __future__ import annotations

import datetime
import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from lib.cefs.paths import FileWithAge

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class ImageAgeFilterResult:
    """Result of filtering images by age."""

    old_enough: list[Path]
    too_recent: list[tuple[Path, datetime.timedelta]]


@dataclass(frozen=True)
class ImageDeletionResult:
    """Result of deleting a CEFS image with its manifest."""

    success: bool
    deleted_size: int
    errors: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class GCSummary:
    """Summary statistics for garbage collection."""

    total_images: int
    referenced_images: int
    unreferenced_images: int
    space_to_reclaim: int


def filter_images_by_age(
    images: list[Path], min_age_delta: datetime.timedelta, now: datetime.datetime
) -> ImageAgeFilterResult:
    """Filter images by age, separating old enough from too recent.

    Args:
        images: List of image paths to filter
        min_age_delta: Minimum age for deletion
        now: Current time to use for age calculation

    Returns:
        ImageAgeFilterResult with old_enough and too_recent lists
    """
    old_enough = []
    too_recent = []

    for image_path in images:
        try:
            mtime = datetime.datetime.fromtimestamp(image_path.stat().st_mtime)
            age = now - mtime
            if age >= min_age_delta:
                old_enough.append(image_path)
            else:
                too_recent.append((image_path, age))
        except OSError:
            # If we can't stat it, include it as potentially broken
            old_enough.append(image_path)

    return ImageAgeFilterResult(old_enough=old_enough, too_recent=too_recent)


def delete_image_with_manifest(image_path: Path) -> ImageDeletionResult:
    """Delete a CEFS image and its associated manifest file.

    Args:
        image_path: Path to the CEFS image to delete

    Returns:
        ImageDeletionResult with success status, size, and any errors
    """
    errors = []
    deleted_size = 0

    # Get size before deletion
    try:
        deleted_size = image_path.stat().st_size
    except OSError as e:
        errors.append(f"Could not stat {image_path}: {e}")
        # Try to delete anyway

    # Delete the image
    try:
        image_path.unlink()
    except OSError as e:
        errors.append(f"Failed to delete {image_path}: {e}")
        return ImageDeletionResult(success=False, deleted_size=0, errors=errors)

    # Delete the manifest if it exists
    manifest_path = image_path.with_suffix(".yaml")
    if manifest_path.exists():
        try:
            manifest_path.unlink()
        except OSError as e:
            errors.append(f"Failed to delete manifest {manifest_path}: {e}")
            # This is non-fatal - image was deleted

    return ImageDeletionResult(success=True, deleted_size=deleted_size, errors=errors)


@dataclass(frozen=True)
class BakCleanupResult:
    """Result of cleaning up .bak and .DELETE_ME_* items."""

    deleted_count: int
    skipped_too_recent: int
    errors: list[str] = field(default_factory=list)


def delete_bak_item(item_path: Path) -> str | None:
    """Delete a single .bak or .DELETE_ME_* item (file, symlink, or directory tree).

    Returns an error message on failure, or None on success.
    """
    try:
        if item_path.is_symlink() or item_path.is_file():
            item_path.unlink()
        elif item_path.is_dir():
            shutil.rmtree(item_path)
        else:
            return f"Unknown file type, cannot delete: {item_path}"
    except OSError as e:
        return f"Failed to delete {item_path}: {e}"
    return None


def cleanup_bak_items(
    items: list[FileWithAge],
    min_age_seconds: float,
    dry_run: bool,
) -> BakCleanupResult:
    """Clean up .bak and .DELETE_ME_* items older than min_age.

    Args:
        items: List of FileWithAge items to consider
        min_age_seconds: Minimum age in seconds before an item is eligible for deletion
        dry_run: If True, only report what would be deleted

    Returns:
        BakCleanupResult with counts and any errors
    """
    deleted_count = 0
    skipped_too_recent = 0
    errors = []

    for item in items:
        if item.age_seconds < min_age_seconds:
            skipped_too_recent += 1
            _LOGGER.info(
                "Skipping recent item (age %s): %s",
                datetime.timedelta(seconds=int(item.age_seconds)),
                item.path,
            )
            continue

        age_str = str(datetime.timedelta(seconds=int(item.age_seconds)))
        if dry_run:
            _LOGGER.info("Would delete: %s (age: %s)", item.path, age_str)
            deleted_count += 1
            continue

        _LOGGER.info("Deleting: %s (age: %s)", item.path, age_str)
        error = delete_bak_item(item.path)
        if error:
            errors.append(error)
            _LOGGER.error(error)
        else:
            deleted_count += 1

    return BakCleanupResult(
        deleted_count=deleted_count,
        skipped_too_recent=skipped_too_recent,
        errors=errors,
    )


def check_if_symlink_references_image(symlink_path: Path, image_stem: str, mount_point: Path) -> bool:
    if not symlink_path.is_symlink():
        return False

    try:
        target = symlink_path.readlink()
        if target.is_absolute() and target.is_relative_to(mount_point):
            mount_parts_len = len(mount_point.parts)
            parts = target.parts
            if len(parts) >= mount_parts_len + 2:
                # The directory name is at index mount_parts_len + 1
                # e.g., for /cefs/0d/0d163f7f3ee984e50fd7d14f_consolidated/subdir
                # parts[mount_parts_len + 1] is "0d163f7f3ee984e50fd7d14f_consolidated"
                target_dir = parts[mount_parts_len + 1]
                return target_dir == image_stem
    except (OSError, IndexError):
        pass

    return False
