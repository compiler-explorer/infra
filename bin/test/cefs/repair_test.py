#!/usr/bin/env python3
"""Tests for CEFS repair functionality."""

from __future__ import annotations

import datetime
import os
import time
from pathlib import Path
from unittest.mock import Mock, patch

import yaml
from lib.cefs.repair import (
    InProgressTransaction,
    RepairAction,
    TransactionStatus,
    analyze_all_incomplete_transactions,
    analyze_incomplete_transaction,
    perform_delete,
    perform_finalize,
)

from test.cefs.test_helpers import make_test_manifest


def test_fully_complete_transaction(tmp_path):
    """Test analysis of a fully complete transaction."""
    nfs_dir = tmp_path / "nfs"
    cefs_image_dir = tmp_path / "cefs-images"
    mount_point = tmp_path / "cefs"
    nfs_dir.mkdir()
    cefs_image_dir.mkdir()
    mount_point.mkdir()

    # Create test image and inprogress manifest
    image_hash = "abc123_test"
    subdir = cefs_image_dir / image_hash[:2]
    subdir.mkdir()
    image_path = subdir / f"{image_hash}.sqfs"
    image_path.touch()
    inprogress_path = subdir / f"{image_hash}.yaml.inprogress"

    # Create manifest with absolute paths to temp nfs_dir
    manifest = make_test_manifest(
        contents=[
            {"destination": str(nfs_dir / "gcc-12")},
            {"destination": str(nfs_dir / "gcc-13")},
        ]
    )
    inprogress_path.write_text(yaml.dump(manifest))

    # Make it old enough
    old_time = time.time() - (2 * 3600)
    os.utime(inprogress_path, (old_time, old_time))

    # Create symlinks pointing to the image
    (nfs_dir / "gcc-12").symlink_to(f"{mount_point}/{image_hash[:2]}/{image_hash}")
    (nfs_dir / "gcc-13").symlink_to(f"{mount_point}/{image_hash[:2]}/{image_hash}")

    # Analyze the transaction - no mocking!
    result = analyze_incomplete_transaction(
        inprogress_path,
        nfs_dir,
        mount_point,
        3600,  # 1 hour min age
        datetime.datetime.now(),
    )

    assert result.status == TransactionStatus.FULLY_COMPLETE
    assert result.action == RepairAction.FINALIZE
    assert len(result.existing_symlinks) == 2
    assert len(result.missing_symlinks) == 0


def test_partially_complete_transaction(tmp_path):
    """Test analysis of a partially complete transaction."""
    nfs_dir = tmp_path / "nfs"
    cefs_image_dir = tmp_path / "cefs-images"
    mount_point = tmp_path / "cefs"
    nfs_dir.mkdir()
    cefs_image_dir.mkdir()
    mount_point.mkdir()

    # Create test image and inprogress manifest
    image_hash = "def456_test"
    subdir = cefs_image_dir / image_hash[:2]
    subdir.mkdir()
    image_path = subdir / f"{image_hash}.sqfs"
    image_path.touch()
    inprogress_path = subdir / f"{image_hash}.yaml.inprogress"

    # Create manifest with three destinations
    manifest = make_test_manifest(
        contents=[
            {"destination": str(nfs_dir / "gcc-12")},
            {"destination": str(nfs_dir / "gcc-13")},
            {"destination": str(nfs_dir / "gcc-14")},
        ]
    )
    inprogress_path.write_text(yaml.dump(manifest))

    # Make it old enough
    old_time = time.time() - (2 * 3600)
    os.utime(inprogress_path, (old_time, old_time))

    # Create only first two symlinks (partial completion)
    (nfs_dir / "gcc-12").symlink_to(f"{mount_point}/{image_hash[:2]}/{image_hash}")
    (nfs_dir / "gcc-13").symlink_to(f"{mount_point}/{image_hash[:2]}/{image_hash}")
    # gcc-14 is NOT created

    # Analyze the transaction - no mocking!
    result = analyze_incomplete_transaction(
        inprogress_path,
        nfs_dir,
        mount_point,
        3600,
        datetime.datetime.now(),
    )

    assert result.status == TransactionStatus.PARTIALLY_COMPLETE
    assert result.action == RepairAction.FINALIZE
    assert len(result.existing_symlinks) == 2
    assert len(result.missing_symlinks) == 1


def test_failed_early_transaction(tmp_path):
    """Test analysis of a transaction that failed early (no symlinks)."""
    nfs_dir = tmp_path / "nfs"
    cefs_image_dir = tmp_path / "cefs-images"
    mount_point = tmp_path / "cefs"
    nfs_dir.mkdir()
    cefs_image_dir.mkdir()
    mount_point.mkdir()

    # Create test image and inprogress manifest
    image_hash = "ghi789_test"
    subdir = cefs_image_dir / image_hash[:2]
    subdir.mkdir()
    image_path = subdir / f"{image_hash}.sqfs"
    image_path.touch()
    inprogress_path = subdir / f"{image_hash}.yaml.inprogress"

    # Create manifest with destination
    manifest = make_test_manifest(contents=[{"destination": str(nfs_dir / "clang-15")}])
    inprogress_path.write_text(yaml.dump(manifest))

    # Make it old enough
    old_time = time.time() - (2 * 3600)
    os.utime(inprogress_path, (old_time, old_time))

    # No symlinks created - transaction failed early

    # Analyze the transaction - no mocking!
    result = analyze_incomplete_transaction(
        inprogress_path,
        nfs_dir,
        mount_point,
        3600,
        datetime.datetime.now(),
    )

    assert result.status == TransactionStatus.FAILED_EARLY
    assert result.action == RepairAction.DELETE
    assert len(result.existing_symlinks) == 0
    assert len(result.missing_symlinks) == 1


def test_too_recent_transaction(tmp_path):
    """Test analysis of a transaction that is too recent."""
    nfs_dir = tmp_path / "nfs"
    cefs_image_dir = tmp_path / "cefs-images"
    mount_point = tmp_path / "cefs"
    nfs_dir.mkdir()
    cefs_image_dir.mkdir()
    mount_point.mkdir()

    # Create test image and inprogress manifest
    image_hash = "jkl012_test"
    subdir = cefs_image_dir / image_hash[:2]
    subdir.mkdir()
    image_path = subdir / f"{image_hash}.sqfs"
    image_path.touch()
    inprogress_path = subdir / f"{image_hash}.yaml.inprogress"

    # Create manifest
    manifest = make_test_manifest(contents=[{"destination": str(nfs_dir / "gcc-15")}])
    inprogress_path.write_text(yaml.dump(manifest))

    # Keep it recent (30 minutes old)
    recent_time = time.time() - (30 * 60)
    os.utime(inprogress_path, (recent_time, recent_time))

    # No symlinks created

    # Analyze the transaction - no mocking!
    result = analyze_incomplete_transaction(
        inprogress_path,
        nfs_dir,
        mount_point,
        3600,  # 1 hour min age
        datetime.datetime.now(),
    )

    assert result.status == TransactionStatus.TOO_RECENT
    assert result.action == RepairAction.SKIP


def test_missing_image_file(tmp_path):
    """Test analysis when the squashfs image file is missing."""
    nfs_dir = tmp_path / "nfs"
    cefs_image_dir = tmp_path / "cefs-images"
    mount_point = tmp_path / "cefs"
    nfs_dir.mkdir()
    cefs_image_dir.mkdir()
    mount_point.mkdir()

    # Create inprogress manifest WITHOUT image file
    image_hash = "mno345_test"
    subdir = cefs_image_dir / image_hash[:2]
    subdir.mkdir()
    inprogress_path = subdir / f"{image_hash}.yaml.inprogress"
    # Note: NOT creating the .sqfs file

    # Create manifest
    manifest = make_test_manifest(contents=[{"destination": str(nfs_dir / "gcc-12")}])
    inprogress_path.write_text(yaml.dump(manifest))

    # Make it old enough
    old_time = time.time() - (2 * 3600)
    os.utime(inprogress_path, (old_time, old_time))

    result = analyze_incomplete_transaction(
        inprogress_path,
        nfs_dir,
        mount_point,
        3600,
        datetime.datetime.now(),
    )

    # Should still mark for deletion if old enough
    assert result.status == TransactionStatus.FAILED_EARLY
    assert result.action == RepairAction.DELETE


def test_bak_symlink_protection(tmp_path):
    """Test that .bak symlinks are properly detected and protect the image."""
    nfs_dir = tmp_path / "nfs"
    cefs_image_dir = tmp_path / "cefs-images"
    mount_point = tmp_path / "cefs"
    nfs_dir.mkdir()
    cefs_image_dir.mkdir()
    mount_point.mkdir()

    # Create test image and inprogress manifest
    image_hash = "bak123_test"
    subdir = cefs_image_dir / image_hash[:2]
    subdir.mkdir()
    image_path = subdir / f"{image_hash}.sqfs"
    image_path.touch()
    inprogress_path = subdir / f"{image_hash}.yaml.inprogress"

    # Create manifest
    manifest = make_test_manifest(contents=[{"destination": str(nfs_dir / "gcc-16")}])
    inprogress_path.write_text(yaml.dump(manifest))

    # Make it old enough
    old_time = time.time() - (2 * 3600)
    os.utime(inprogress_path, (old_time, old_time))

    # Create only the .bak symlink (simulating a rollback scenario)
    (nfs_dir / "gcc-16.bak").symlink_to(f"{mount_point}/{image_hash[:2]}/{image_hash}")
    # Main symlink does NOT exist

    # Analyze the transaction
    result = analyze_incomplete_transaction(
        inprogress_path,
        nfs_dir,
        mount_point,
        3600,
        datetime.datetime.now(),
    )

    # Should detect the .bak symlink and mark for finalization
    assert result.status == TransactionStatus.FULLY_COMPLETE
    assert result.action == RepairAction.FINALIZE
    assert len(result.existing_symlinks) == 1
    assert result.existing_symlinks[0] == nfs_dir / "gcc-16.bak"


def test_perform_finalize_success(tmp_path):
    """Test successful finalization."""
    cefs_image_dir = tmp_path / "cefs-images"
    cefs_image_dir.mkdir()
    subdir = cefs_image_dir / "ab"
    subdir.mkdir()

    image_path = subdir / "test.sqfs"
    image_path.touch()
    inprogress_path = subdir / "test.yaml.inprogress"
    inprogress_path.write_text("dummy manifest content")

    transaction = Mock(spec=InProgressTransaction)
    transaction.image_path = image_path
    transaction.inprogress_path = inprogress_path

    result = perform_finalize(transaction, dry_run=False)

    assert result is True
    assert not inprogress_path.exists()
    assert (subdir / "test.yaml").exists()
    assert (subdir / "test.yaml").read_text() == "dummy manifest content"


def test_perform_finalize_dry_run(tmp_path):
    """Test finalization in dry-run mode."""
    cefs_image_dir = tmp_path / "cefs-images"
    cefs_image_dir.mkdir()
    subdir = cefs_image_dir / "ab"
    subdir.mkdir()

    image_path = subdir / "test.sqfs"
    image_path.touch()
    inprogress_path = subdir / "test.yaml.inprogress"
    inprogress_path.write_text("dummy manifest content")

    transaction = Mock(spec=InProgressTransaction)
    transaction.image_path = image_path
    transaction.inprogress_path = inprogress_path

    result = perform_finalize(transaction, dry_run=True)

    assert result is True
    assert inprogress_path.exists()  # Should NOT be renamed
    assert not (subdir / "test.yaml").exists()


def test_perform_finalize_failure():
    """Test finalization failure."""
    transaction = Mock(spec=InProgressTransaction)
    transaction.image_path = Path("/efs/cefs-images/ab/test.sqfs")
    transaction.inprogress_path = Path("/efs/cefs-images/ab/test.yaml.inprogress")

    # Mock finalize_manifest to raise an OSError
    with patch("lib.cefs.repair.finalize_manifest", side_effect=OSError("Failed to rename")):
        result = perform_finalize(transaction, dry_run=False)

    assert result is False


def test_perform_delete_success(tmp_path):
    """Test successful deletion."""
    cefs_image_dir = tmp_path / "cefs-images"
    cefs_image_dir.mkdir()
    subdir = cefs_image_dir / "ab"
    subdir.mkdir()

    image_path = subdir / "test.sqfs"
    image_path.write_text("image content")
    inprogress_path = subdir / "test.yaml.inprogress"
    inprogress_path.write_text("manifest content")

    transaction = Mock(spec=InProgressTransaction)
    transaction.image_path = image_path
    transaction.inprogress_path = inprogress_path

    result = perform_delete(transaction, dry_run=False)

    assert result is True
    assert not image_path.exists()
    assert not inprogress_path.exists()


def test_perform_delete_dry_run(tmp_path):
    """Test deletion in dry-run mode."""
    cefs_image_dir = tmp_path / "cefs-images"
    cefs_image_dir.mkdir()
    subdir = cefs_image_dir / "ab"
    subdir.mkdir()

    image_path = subdir / "test.sqfs"
    image_path.write_text("image content")
    inprogress_path = subdir / "test.yaml.inprogress"
    inprogress_path.write_text("manifest content")

    transaction = Mock(spec=InProgressTransaction)
    transaction.image_path = image_path
    transaction.inprogress_path = inprogress_path

    result = perform_delete(transaction, dry_run=True)

    assert result is True
    assert image_path.exists()  # Should NOT be deleted
    assert inprogress_path.exists()  # Should NOT be deleted


def test_perform_delete_missing_image(tmp_path):
    """Test deletion when image file doesn't exist."""
    cefs_image_dir = tmp_path / "cefs-images"
    cefs_image_dir.mkdir()
    subdir = cefs_image_dir / "ab"
    subdir.mkdir()

    image_path = subdir / "test.sqfs"
    # Note: NOT creating the image file
    inprogress_path = subdir / "test.yaml.inprogress"
    inprogress_path.write_text("manifest content")

    transaction = Mock(spec=InProgressTransaction)
    transaction.image_path = image_path
    transaction.inprogress_path = inprogress_path

    result = perform_delete(transaction, dry_run=False)

    assert result is True  # Should still succeed
    assert not inprogress_path.exists()  # Manifest should be deleted


def test_categorize_transactions(tmp_path):
    """Test categorization of multiple transactions."""
    nfs_dir = tmp_path / "nfs"
    cefs_image_dir = tmp_path / "cefs-images"
    mount_point = tmp_path / "cefs"
    nfs_dir.mkdir()
    cefs_image_dir.mkdir()
    mount_point.mkdir()

    # Create three transactions with different states

    # 1. Transaction to finalize (old, with symlinks)
    hash1 = "final123_test"
    subdir1 = cefs_image_dir / hash1[:2]
    subdir1.mkdir()
    image1 = subdir1 / f"{hash1}.sqfs"
    image1.write_bytes(b"x" * 1000)  # 1KB file
    inprogress1 = subdir1 / f"{hash1}.yaml.inprogress"
    manifest1 = make_test_manifest(contents=[{"destination": str(nfs_dir / "gcc-20")}])
    inprogress1.write_text(yaml.dump(manifest1))
    old_time = time.time() - (2 * 3600)
    os.utime(inprogress1, (old_time, old_time))
    (nfs_dir / "gcc-20").symlink_to(f"{mount_point}/{hash1[:2]}/{hash1}")

    # 2. Transaction to delete (old, no symlinks)
    hash2 = "delete456_test"
    subdir2 = cefs_image_dir / hash2[:2]
    subdir2.mkdir()
    image2 = subdir2 / f"{hash2}.sqfs"
    image2.write_bytes(b"y" * 2000)  # 2KB file
    inprogress2 = subdir2 / f"{hash2}.yaml.inprogress"
    manifest2 = make_test_manifest(contents=[{"destination": str(nfs_dir / "clang-20")}])
    inprogress2.write_text(yaml.dump(manifest2))
    os.utime(inprogress2, (old_time, old_time))
    # No symlink created

    # 3. Transaction to skip (too recent)
    hash3 = "skip789_test"
    subdir3 = cefs_image_dir / hash3[:2]
    subdir3.mkdir()
    image3 = subdir3 / f"{hash3}.sqfs"
    image3.touch()
    inprogress3 = subdir3 / f"{hash3}.yaml.inprogress"
    manifest3 = make_test_manifest(contents=[{"destination": str(nfs_dir / "rust-2")}])
    inprogress3.write_text(yaml.dump(manifest3))
    recent_time = time.time() - (30 * 60)  # 30 minutes old
    os.utime(inprogress3, (recent_time, recent_time))

    inprogress_files = [inprogress1, inprogress2, inprogress3]

    summary = analyze_all_incomplete_transactions(
        inprogress_files,
        nfs_dir,
        mount_point,
        3600,
        datetime.datetime.now(),
    )

    assert len(summary.to_finalize) == 1
    assert len(summary.to_delete) == 1
    assert len(summary.to_skip) == 1
    assert summary.total_space_to_free == 2000  # Size of the image to delete
