#!/usr/bin/env python3
"""CEFS filesystem repair operations for incomplete transactions."""

from __future__ import annotations

import datetime
import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import humanfriendly
import yaml
from lib.cefs.gc import check_if_symlink_references_image
from lib.cefs_manifest import finalize_manifest

_LOGGER = logging.getLogger(__name__)


class TransactionStatus(Enum):
    """Status of an incomplete CEFS transaction."""

    FULLY_COMPLETE = "fully_complete"  # All symlinks exist - can finalize
    PARTIALLY_COMPLETE = "partially_complete"  # Some symlinks exist - can finalize
    FAILED_EARLY = "failed_early"  # No symlinks exist - should delete
    CONFLICTED = "conflicted"  # Symlinks point elsewhere - needs manual intervention
    TOO_RECENT = "too_recent"  # Younger than min-age threshold


class RepairAction(Enum):
    """Action to take for repairing an incomplete transaction."""

    FINALIZE = "finalize"  # Rename .yaml.inprogress -> .yaml
    DELETE = "delete"  # Remove image and .inprogress file
    SKIP = "skip"  # Too recent or conflicted


@dataclass(frozen=True)
class InProgressTransaction:
    """Represents an incomplete CEFS transaction."""

    inprogress_path: Path
    image_path: Path
    manifest: dict
    age_seconds: float
    status: TransactionStatus
    existing_symlinks: list[Path]
    missing_symlinks: list[Path]
    conflicted_symlinks: list[Path]
    action: RepairAction

    @property
    def total_destinations(self) -> int:
        """Total number of expected symlinks."""
        return len(self.existing_symlinks) + len(self.missing_symlinks) + len(self.conflicted_symlinks)

    @property
    def age_str(self) -> str:
        """Human-readable age string."""
        return humanfriendly.format_timespan(self.age_seconds)


@dataclass(frozen=True)
class RepairSummary:
    """Summary of repair operations to perform."""

    to_finalize: list[InProgressTransaction]
    to_delete: list[InProgressTransaction]
    to_skip: list[InProgressTransaction]
    total_space_to_free: int


def analyze_incomplete_transaction(
    inprogress_path: Path,
    nfs_dir: Path,
    mount_point: Path,
    min_age_seconds: float,
    now: datetime.datetime,
) -> InProgressTransaction:
    """Analyze an incomplete transaction to determine its state and repair action.

    Args:
        inprogress_path: Path to .yaml.inprogress file
        nfs_dir: Base NFS directory
        mount_point: CEFS mount point
        min_age_seconds: Minimum age in seconds before repair
        now: Current time for age calculation

    Returns:
        InProgressTransaction with analysis results
    """
    # Calculate age
    try:
        mtime = datetime.datetime.fromtimestamp(inprogress_path.stat().st_mtime)
        age = now - mtime
        age_seconds = age.total_seconds()
    except OSError as e:
        _LOGGER.warning("Could not stat %s: %s - treating as old", inprogress_path, e)
        age_seconds = min_age_seconds + 1  # Treat as old enough if we can't stat

    # Read manifest
    try:
        with inprogress_path.open(encoding="utf-8") as f:
            manifest = yaml.safe_load(f)
    except (OSError, yaml.YAMLError) as e:
        _LOGGER.error("Cannot read manifest %s: %s", inprogress_path, e)
        # Can't analyze without manifest
        return InProgressTransaction(
            inprogress_path=inprogress_path,
            image_path=inprogress_path.with_suffix("").with_suffix(".sqfs"),
            manifest={},
            age_seconds=age_seconds,
            status=TransactionStatus.CONFLICTED,
            existing_symlinks=[],
            missing_symlinks=[],
            conflicted_symlinks=[],
            action=RepairAction.SKIP,
        )

    # Get expected image path
    image_path = inprogress_path.with_suffix("").with_suffix(".sqfs")
    if not image_path.exists():
        _LOGGER.warning("Image file missing for %s", inprogress_path)
        # If image doesn't exist, we should delete the orphaned .inprogress file
        return InProgressTransaction(
            inprogress_path=inprogress_path,
            image_path=image_path,
            manifest=manifest,
            age_seconds=age_seconds,
            status=TransactionStatus.FAILED_EARLY if age_seconds >= min_age_seconds else TransactionStatus.TOO_RECENT,
            existing_symlinks=[],
            missing_symlinks=[],
            conflicted_symlinks=[],
            action=RepairAction.DELETE if age_seconds >= min_age_seconds else RepairAction.SKIP,
        )

    # Extract image stem for checking symlinks
    image_stem = image_path.stem

    # Check each expected destination
    existing_symlinks = []
    missing_symlinks = []
    conflicted_symlinks = []

    contents = manifest.get("contents", [])
    for content in contents:
        destination = content.get("destination")
        if not destination:
            continue

        dest_path = Path(destination)

        if check_if_symlink_references_image(dest_path, image_stem, mount_point):
            existing_symlinks.append(dest_path)
            continue

        # During rollback operations, the active symlink might be swapped with .bak
        # We must check both to avoid deleting an image that's still referenced
        bak_path = dest_path.with_name(dest_path.name + ".bak")
        if check_if_symlink_references_image(bak_path, image_stem, mount_point):
            existing_symlinks.append(bak_path)
            continue

        # If a symlink exists but points to a different image, this is a conflict
        # (the destination was updated to a newer image after this transaction started)
        if dest_path.is_symlink():
            try:
                target = dest_path.readlink()
                conflicted_symlinks.append(dest_path)
                _LOGGER.debug("Symlink %s points elsewhere: %s", dest_path, target)
            except OSError as e:
                # Broken symlink - can't read target
                _LOGGER.warning("Cannot read symlink target for %s: %s", dest_path, e)
                missing_symlinks.append(dest_path)
        else:
            missing_symlinks.append(dest_path)

    # Based on the symlink state, determine the appropriate repair action:
    # - Too recent: Still might be in progress, don't touch
    # - Conflicted: Manual intervention needed (symlinks point elsewhere)
    # - Fully/Partially complete: Can finalize (rename .inprogress -> .yaml)
    # - Failed early: Safe to delete (no symlinks created)
    if age_seconds < min_age_seconds:
        status = TransactionStatus.TOO_RECENT
        action = RepairAction.SKIP
    elif conflicted_symlinks:
        status = TransactionStatus.CONFLICTED
        action = RepairAction.SKIP
    elif existing_symlinks and not missing_symlinks:
        status = TransactionStatus.FULLY_COMPLETE
        action = RepairAction.FINALIZE
    elif existing_symlinks:
        status = TransactionStatus.PARTIALLY_COMPLETE
        action = RepairAction.FINALIZE
    elif not existing_symlinks:
        status = TransactionStatus.FAILED_EARLY
        action = RepairAction.DELETE
    else:
        # This indicates a logic error - we have symlinks but an unexpected combination
        # Log as error so it gets noticed and fixed
        _LOGGER.error(
            "BUG: Unexpected transaction state for %s - existing=%d, missing=%d, conflicted=%d",
            inprogress_path,
            len(existing_symlinks),
            len(missing_symlinks),
            len(conflicted_symlinks),
        )
        status = TransactionStatus.CONFLICTED
        action = RepairAction.SKIP

    return InProgressTransaction(
        inprogress_path=inprogress_path,
        image_path=image_path,
        manifest=manifest,
        age_seconds=age_seconds,
        status=status,
        existing_symlinks=existing_symlinks,
        missing_symlinks=missing_symlinks,
        conflicted_symlinks=conflicted_symlinks,
        action=action,
    )


def analyze_all_incomplete_transactions(
    inprogress_files: list[Path],
    nfs_dir: Path,
    mount_point: Path,
    min_age_seconds: float,
    now: datetime.datetime,
) -> RepairSummary:
    """Analyze all incomplete transactions and categorize them for repair.

    Args:
        inprogress_files: List of .yaml.inprogress files
        nfs_dir: Base NFS directory
        mount_point: CEFS mount point
        min_age_seconds: Minimum age in seconds before repair
        now: Current time for age calculation

    Returns:
        RepairSummary with categorized transactions
    """
    to_finalize = []
    to_delete = []
    to_skip = []
    total_space_to_free = 0

    for inprogress_path in inprogress_files:
        transaction = analyze_incomplete_transaction(inprogress_path, nfs_dir, mount_point, min_age_seconds, now)

        if transaction.action == RepairAction.FINALIZE:
            to_finalize.append(transaction)
        elif transaction.action == RepairAction.DELETE:
            to_delete.append(transaction)
            if transaction.image_path.exists():
                try:
                    total_space_to_free += transaction.image_path.stat().st_size
                except OSError as e:
                    _LOGGER.warning("Cannot stat image %s for space calculation: %s", transaction.image_path, e)
        else:
            to_skip.append(transaction)

    return RepairSummary(
        to_finalize=to_finalize,
        to_delete=to_delete,
        to_skip=to_skip,
        total_space_to_free=total_space_to_free,
    )


def perform_finalize(transaction: InProgressTransaction, dry_run: bool = False) -> bool:
    """Finalize a transaction by renaming .yaml.inprogress to .yaml.

    Args:
        transaction: Transaction to finalize
        dry_run: If True, only log what would be done

    Returns:
        True if successful
    """
    if dry_run:
        _LOGGER.info("DRY RUN: Would finalize %s", transaction.inprogress_path)
        return True

    try:
        finalize_manifest(transaction.image_path)
        _LOGGER.info("Finalized: %s", transaction.inprogress_path.with_suffix("").with_suffix(".yaml"))
        return True
    except (OSError, FileNotFoundError) as e:
        _LOGGER.error("Failed to finalize %s: %s", transaction.inprogress_path, e)
        return False


def perform_delete(transaction: InProgressTransaction, dry_run: bool = False) -> bool:
    """Delete a failed transaction's image and manifest files.

    Args:
        transaction: Transaction to delete
        dry_run: If True, only log what would be done

    Returns:
        True if successful
    """
    if dry_run:
        _LOGGER.info("DRY RUN: Would delete %s and %s", transaction.image_path, transaction.inprogress_path)
        return True

    success = True

    # Delete image if it exists
    if transaction.image_path.exists():
        try:
            transaction.image_path.unlink()
            _LOGGER.info("Deleted image: %s", transaction.image_path)
        except OSError as e:
            _LOGGER.error("Failed to delete image %s: %s", transaction.image_path, e)
            success = False

    # Delete .inprogress file
    try:
        transaction.inprogress_path.unlink()
        _LOGGER.info("Deleted manifest: %s", transaction.inprogress_path)
    except OSError as e:
        _LOGGER.error("Failed to delete manifest %s: %s", transaction.inprogress_path, e)
        success = False

    return success
