#!/usr/bin/env python3
"""Tests for CEFS deployment module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock, patch

from lib.cefs.deployment import (
    check_temp_space_available,
    deploy_to_cefs_transactional,
    has_enough_space,
    snapshot_symlink_targets,
    verify_symlinks_unchanged,
)

from test.cefs_test_helpers import make_test_manifest


def test_has_enough_space():
    # Test with enough space
    assert has_enough_space(1000 * 1024 * 1024, 500 * 1024 * 1024) is True  # 1000MB available, 500MB required

    # Test with exactly enough space
    assert has_enough_space(1000 * 1024 * 1024, 1000 * 1024 * 1024) is True  # 1000MB = 1000MB

    # Test with not enough space
    assert has_enough_space(500 * 1024 * 1024, 1000 * 1024 * 1024) is False  # 500MB < 1000MB required

    # Test edge cases
    assert has_enough_space(0, 0) is True  # No space needed
    assert has_enough_space(1, 0) is True  # No space needed
    assert has_enough_space(0, 1) is False  # Need space but have none


@patch("os.statvfs")
def test_check_temp_space_available(mock_statvfs):
    # Mock filesystem stats
    mock_stat = Mock()
    mock_stat.f_bavail = 1000  # Available blocks
    mock_stat.f_frsize = 1024 * 1024  # Block size in bytes (1MB)
    mock_statvfs.return_value = mock_stat

    temp_dir = Path("/tmp/test")

    # Test sufficient space (1000MB available, need 500MB)
    assert check_temp_space_available(temp_dir, 500 * 1024 * 1024) is True

    # Test insufficient space (1000MB available, need 1500MB)
    assert check_temp_space_available(temp_dir, 1500 * 1024 * 1024) is False


@patch("os.statvfs")
def test_check_temp_space_os_error(mock_statvfs):
    mock_statvfs.side_effect = OSError("Permission denied")

    temp_dir = Path("/invalid/path")
    assert check_temp_space_available(temp_dir, 1024) is False


def test_snapshot_symlink_targets(tmp_path):
    # Create symlinks pointing to (non-existent) CEFS paths
    # This is fine - symlinks can point to non-existent targets
    link1 = tmp_path / "gcc-4.5"
    link2 = tmp_path / "boost-1.82"
    link1.symlink_to("/cefs/ab/abc123")
    link2.symlink_to("/cefs/cd/cdef456")

    result = snapshot_symlink_targets([link1, link2])

    expected = {link1: Path("/cefs/ab/abc123"), link2: Path("/cefs/cd/cdef456")}
    assert result == expected


def test_snapshot_symlink_targets_with_errors(tmp_path):
    link1 = tmp_path / "gcc-4.5"
    link2 = tmp_path / "boost-1.82"
    regular_file = tmp_path / "not-a-symlink"

    link1.symlink_to("/cefs/ab/abc123")
    link2.symlink_to("/cefs/cd/cdef456")
    regular_file.touch()  # Regular file, not a symlink

    result = snapshot_symlink_targets([link1, link2, regular_file])

    # Should only capture actual symlinks
    expected = {link1: Path("/cefs/ab/abc123"), link2: Path("/cefs/cd/cdef456")}
    assert result == expected


def test_verify_symlinks_unchanged(tmp_path):
    link1 = tmp_path / "gcc-4.5"
    link2 = tmp_path / "boost-1.82"

    # Create initial symlinks
    link1.symlink_to("/cefs/ab/abc123")
    link2.symlink_to("/cefs/cd/cdef456")

    # Take snapshot
    snapshot = {link1: Path("/cefs/ab/abc123"), link2: Path("/cefs/cd/cdef456")}

    # Change second symlink to simulate race condition
    link2.unlink()
    link2.symlink_to("/cefs/ef/efgh789")

    unchanged, changed = verify_symlinks_unchanged(snapshot)

    assert unchanged == [link1]  # First unchanged
    assert changed == [link2]  # Second changed


def test_verify_symlinks_nonexistent(tmp_path):
    link = tmp_path / "gcc-4.5"
    link.symlink_to("/cefs/ab/abc123")

    # Snapshot with the symlink
    snapshot = {link: Path("/cefs/ab/abc123")}

    # Remove the symlink
    link.unlink()

    unchanged, changed = verify_symlinks_unchanged(snapshot)

    assert unchanged == []
    assert changed == [link]


def test_deploy_to_cefs_transactional_success(tmp_path):
    """Test that transactional deployment finalizes manifest on success."""
    source_path = tmp_path / "source.sqfs"
    source_path.write_bytes(b"test content")

    cefs_dir = tmp_path / "cefs"
    cefs_dir.mkdir()
    subdir = cefs_dir / "ab"
    subdir.mkdir()
    target_path = subdir / "abc123.sqfs"

    manifest = make_test_manifest()

    # Deploy with successful transaction
    with deploy_to_cefs_transactional(source_path, target_path, manifest, dry_run=False):
        # Simulate work done within the transaction
        pass

    # Verify image was copied
    assert target_path.exists()
    assert target_path.read_bytes() == b"test content"

    # Verify manifest was finalized
    final_manifest = target_path.with_suffix(".yaml")
    assert final_manifest.exists()

    # Verify .inprogress was removed
    inprogress_path = Path(str(target_path.with_suffix(".yaml")) + ".inprogress")
    assert not inprogress_path.exists()


def test_deploy_to_cefs_transactional_failure(tmp_path):
    """Test that transactional deployment leaves .inprogress on failure."""
    source_path = tmp_path / "source.sqfs"
    source_path.write_bytes(b"test content")

    cefs_dir = tmp_path / "cefs"
    cefs_dir.mkdir()
    subdir = cefs_dir / "ab"
    subdir.mkdir()
    target_path = subdir / "abc123.sqfs"

    manifest = make_test_manifest()

    # Deploy with failing transaction
    try:
        with deploy_to_cefs_transactional(source_path, target_path, manifest, dry_run=False):
            # Simulate failure within the transaction
            raise RuntimeError("Simulated failure")
    except RuntimeError:
        pass  # Expected

    # Verify image was copied
    assert target_path.exists()

    # Verify manifest was NOT finalized
    final_manifest = target_path.with_suffix(".yaml")
    assert not final_manifest.exists()

    # Verify .inprogress was kept for debugging
    inprogress_path = Path(str(target_path.with_suffix(".yaml")) + ".inprogress")
    assert inprogress_path.exists()


def test_deploy_to_cefs_transactional_dry_run(tmp_path):
    """Test that dry run doesn't create any files."""
    source_path = tmp_path / "source.sqfs"
    source_path.write_bytes(b"test content")

    cefs_dir = tmp_path / "cefs"
    cefs_dir.mkdir()
    subdir = cefs_dir / "ab"
    subdir.mkdir()
    target_path = subdir / "abc123.sqfs"

    manifest = make_test_manifest()

    # Deploy in dry-run mode
    with deploy_to_cefs_transactional(source_path, target_path, manifest, dry_run=True):
        pass

    # Verify nothing was created
    assert not target_path.exists()
    assert not target_path.with_suffix(".yaml").exists()
    assert not Path(str(target_path.with_suffix(".yaml")) + ".inprogress").exists()
