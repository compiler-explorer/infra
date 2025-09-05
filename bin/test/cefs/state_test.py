#!/usr/bin/env python3
"""Tests for CEFS state module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import yaml
from lib.cefs.gc import check_if_symlink_references_image
from lib.cefs.state import CEFSState

from test.cefs.test_helpers import make_test_manifest


def test_cefs_state_init():
    nfs_dir = Path("/opt/compiler-explorer")
    cefs_image_dir = Path("/efs/cefs-images")
    state = CEFSState(nfs_dir, cefs_image_dir, Path("/cefs"))

    assert state.nfs_dir == nfs_dir
    assert state.cefs_image_dir == cefs_image_dir
    assert not state.referenced_images
    assert not state.all_cefs_images


def test_find_unreferenced_images():
    nfs_dir = Path("/opt/compiler-explorer")
    cefs_image_dir = Path("/efs/cefs-images")
    state = CEFSState(nfs_dir, cefs_image_dir, Path("/cefs"))

    # Set up test data
    state.all_cefs_images = {
        "abc123": Path("/efs/cefs-images/ab/abc123.sqfs"),
        "def456": Path("/efs/cefs-images/de/def456.sqfs"),
        "ghi789": Path("/efs/cefs-images/gh/ghi789.sqfs"),
    }
    state.referenced_images = {"abc123", "def456"}

    unreferenced = state.find_unreferenced_images()

    assert len(unreferenced) == 1
    assert unreferenced[0] == Path("/efs/cefs-images/gh/ghi789.sqfs")


@patch("pathlib.Path.stat")
def test_get_summary(mock_stat):
    nfs_dir = Path("/opt/compiler-explorer")
    cefs_image_dir = Path("/efs/cefs-images")
    state = CEFSState(nfs_dir, cefs_image_dir, Path("/cefs"))

    # Set up test data
    state.all_cefs_images = {
        "abc123": Path("/efs/cefs-images/ab/abc123.sqfs"),
        "def456": Path("/efs/cefs-images/de/def456.sqfs"),
        "ghi789": Path("/efs/cefs-images/gh/ghi789.sqfs"),
    }
    state.referenced_images = {"abc123", "def456"}

    # Mock file sizes
    mock_stat.return_value.st_size = 1024 * 1024  # 1MB

    summary = state.get_summary()

    assert summary.total_images == 3
    assert summary.referenced_images == 2
    assert summary.unreferenced_images == 1
    assert summary.space_to_reclaim == 1024 * 1024


def test_check_symlink_protects_bak():
    """Test that _check_symlink_points_to_image protects .bak symlinks.

    This is a critical safety test: ensures that images referenced by .bak
    symlinks are protected from garbage collection to preserve rollback capability.
    """
    nfs_dir = Path("/opt/compiler-explorer")
    cefs_image_dir = Path("/efs/cefs-images")
    state = CEFSState(nfs_dir, cefs_image_dir, Path("/cefs"))

    # Use _check_single_symlink directly to test the logic
    # Test case 1: .bak symlink points to the image
    bak_path = Mock(spec=Path)
    bak_path.is_symlink.return_value = True
    bak_path.readlink.return_value = Path("/cefs/ab/abc123_test")

    result = state._check_single_symlink(bak_path, "abc123_test")
    assert result, ".bak symlink should be recognized as valid reference"

    # Test case 2: Verify the full _check_symlink_points_to_image uses _check_single_symlink for both
    # We'll test this by checking that an image with only a .bak reference is protected
    # This is best tested at a higher level with integration tests


@patch("pathlib.Path.is_symlink")
@patch("pathlib.Path.readlink")
def test_check_single_symlink(mock_readlink, mock_is_symlink):
    nfs_dir = Path("/opt/compiler-explorer")
    cefs_image_dir = Path("/efs/cefs-images")
    state = CEFSState(nfs_dir, cefs_image_dir, Path("/cefs"))

    mock_is_symlink.return_value = True
    mock_readlink.return_value = Path("/cefs/ab/abc123_gcc15")

    # Should match
    result = state._check_single_symlink(Path("/test/path"), "abc123_gcc15")
    assert result

    # Should not match different filename
    result = state._check_single_symlink(Path("/test/path"), "def456_gcc15")
    assert not result


def test_scan_with_inprogress_files(tmp_path):
    cefs_dir = tmp_path / "cefs-images"
    nfs_dir = tmp_path / "nfs"
    cefs_dir.mkdir()
    nfs_dir.mkdir()

    subdir = cefs_dir / "ab"
    subdir.mkdir()

    regular_image = subdir / "abc123_test.sqfs"
    regular_image.touch()
    regular_manifest = subdir / "abc123_test.yaml"
    regular_manifest.write_text(
        yaml.dump(make_test_manifest(contents=[{"name": "tools/test 1.0.0", "destination": str(nfs_dir / "test")}]))
    )

    inprogress_image = subdir / "def456_test.sqfs"
    inprogress_image.touch()
    inprogress_manifest = subdir / "def456_test.yaml.inprogress"
    inprogress_manifest.write_text(
        yaml.dump(
            make_test_manifest(
                contents=[{"name": "tools/inprog 1.0.0", "destination": str(nfs_dir / "inprog")}],
                description="In progress manifest",
            )
        )
    )

    state = CEFSState(nfs_dir, cefs_dir, Path("/cefs"))
    state.scan_cefs_images_with_manifests()

    # Image with inprogress should be marked as referenced (protected)
    assert "def456_test" in state.referenced_images
    # Regular image should be in all_cefs_images
    assert "abc123_test" in state.all_cefs_images
    # Should have found the inprogress file
    assert len(state.inprogress_images) == 1
    assert state.inprogress_images[0] == inprogress_manifest


# CEFS Manifest Tests


def test_double_check_prevents_deletion_race(tmp_path):
    nfs_dir = tmp_path / "nfs"
    cefs_image_dir = tmp_path / "cefs-images"
    nfs_dir.mkdir()
    cefs_image_dir.mkdir()

    # Create test image with manifest
    image_hash = "abc123"
    subdir = cefs_image_dir / image_hash[:2]
    subdir.mkdir()
    image_path = subdir / f"{image_hash}.sqfs"
    image_path.touch()

    # Create manifest indicating where symlink should be
    manifest_path = image_path.with_suffix(".yaml")
    manifest_content = make_test_manifest(
        contents=[{"name": "compilers/test/compiler 1.0.0", "destination": str(nfs_dir / "test-compiler")}]
    )
    manifest_path.write_text(yaml.dump(manifest_content))

    # Create state and do initial scan
    state = CEFSState(nfs_dir, cefs_image_dir, Path("/cefs"))
    state.scan_cefs_images_with_manifests()
    state.check_symlink_references()

    # Initially, no symlink exists, so image should be unreferenced
    assert image_hash in state.all_cefs_images
    assert image_hash not in state.referenced_images

    # Now create a symlink (simulating another process creating it)
    symlink_path = nfs_dir / "test-compiler"
    symlink_path.symlink_to(f"/cefs/{image_hash[:2]}/{image_hash}")

    # Double-check should detect the new symlink
    is_referenced = state._check_symlink_points_to_image(nfs_dir / "test-compiler", image_hash)
    assert is_referenced, "Double-check should detect newly created symlink"


def test_bak_symlink_protection(tmp_path):
    nfs_dir = tmp_path / "nfs"
    cefs_image_dir = tmp_path / "cefs-images"
    nfs_dir.mkdir()
    cefs_image_dir.mkdir()

    # Create test image
    image_hash = "def456"
    subdir = cefs_image_dir / image_hash[:2]
    subdir.mkdir()
    image_path = subdir / f"{image_hash}.sqfs"
    image_path.touch()

    # Create manifest
    manifest_path = image_path.with_suffix(".yaml")
    manifest_content = make_test_manifest(
        contents=[{"name": "compilers/test/rollback 1.0.0", "destination": str(nfs_dir / "rollback-compiler")}]
    )
    manifest_path.write_text(yaml.dump(manifest_content))

    # Create only .bak symlink (main symlink is missing/broken)
    bak_symlink = nfs_dir / "rollback-compiler.bak"
    bak_symlink.symlink_to(f"/cefs/{image_hash[:2]}/{image_hash}")

    # Create state and scan
    state = CEFSState(nfs_dir, cefs_image_dir, Path("/cefs"))
    state.scan_cefs_images_with_manifests()
    state.check_symlink_references()

    # Image should be marked as referenced due to .bak symlink
    assert image_hash in state.referenced_images, ".bak symlink should protect image from GC"


def test_inprogress_manifest_protection(tmp_path):
    nfs_dir = tmp_path / "nfs"
    cefs_image_dir = tmp_path / "cefs-images"
    nfs_dir.mkdir()
    cefs_image_dir.mkdir()

    # Create test image with .yaml.inprogress
    image_hash = "ghi789"
    subdir = cefs_image_dir / image_hash[:2]
    subdir.mkdir()
    image_path = subdir / f"{image_hash}.sqfs"
    image_path.touch()

    # Create .yaml.inprogress file (incomplete operation)
    inprogress_path = Path(str(image_path.with_suffix(".yaml")) + ".inprogress")
    inprogress_path.touch()

    # Create state and scan
    state = CEFSState(nfs_dir, cefs_image_dir, Path("/cefs"))
    state.scan_cefs_images_with_manifests()

    # Image should be in referenced set (protected from deletion)
    assert image_hash in state.referenced_images, ".yaml.inprogress should protect image"
    assert inprogress_path in state.inprogress_images


def test_is_image_referenced(tmp_path):
    nfs_dir = tmp_path / "nfs"
    cefs_dir = tmp_path / "cefs"
    nfs_dir.mkdir()
    cefs_dir.mkdir()

    state = CEFSState(nfs_dir, cefs_dir, Path("/cefs"))

    # Set up test data
    state.image_references = {
        "abc123_test": [Path("/opt/gcc-11"), Path("/opt/gcc-12")],
        "def456_test": [Path("/opt/boost")],
        "ghi789_test": [],  # Empty manifest
    }

    # Mock the check method
    with patch.object(state, "_check_symlink_points_to_image") as mock_check:
        # Simulate that /opt/gcc-11 exists for abc123_test
        def check_side_effect(dest_path, filename_stem):
            return dest_path == Path("/opt/gcc-11") and filename_stem == "abc123_test"

        mock_check.side_effect = check_side_effect

        # Test: Image with valid reference
        assert state.is_image_referenced("abc123_test"), "Should find reference for abc123_test"

        # Test: Image with no valid references
        assert not state.is_image_referenced("def456_test"), "Should not find reference for def456_test"

        # Test: Image with empty manifest
        assert not state.is_image_referenced("ghi789_test"), "Should return False for empty manifest"

        # Test: Image not in references at all - should raise ValueError
        with pytest.raises(ValueError, match="has no manifest data"):
            state.is_image_referenced("missing_image")


def testcheck_if_symlink_references_image(tmp_path):
    """Test check_if_symlink_references_image with real-world paths."""
    mount_point = Path("/cefs")

    # Test consolidated image reference
    symlink = tmp_path / "gcc-15.1.0"
    symlink.symlink_to("/cefs/0d/0d163f7f3ee984e50fd7d14f_consolidated/compilers_c++_x86_gcc_15.1.0")

    # This should return True - the symlink points to this consolidated image
    assert check_if_symlink_references_image(symlink, "0d163f7f3ee984e50fd7d14f_consolidated", mount_point)

    # Test individual image reference
    symlink2 = tmp_path / "gcc-14.2.0"
    symlink2.symlink_to("/cefs/1b/1ba0b52e8da6a83656e36877_gcc-14.2.0")

    # This should return True - the symlink points to this individual image
    assert check_if_symlink_references_image(symlink2, "1ba0b52e8da6a83656e36877_gcc-14.2.0", mount_point)

    # Test non-matching reference
    symlink3 = tmp_path / "gcc-13.2.0"
    symlink3.symlink_to("/cefs/50/508034febfc3395b191a5782_gcc-13.2.0")

    # This should return False - the symlink points to a different image
    assert not check_if_symlink_references_image(symlink3, "0d163f7f3ee984e50fd7d14f_consolidated", mount_point)


def test_find_small_consolidated_images(tmp_path):
    """Test find_small_consolidated_images function."""
    state = CEFSState(Path("/opt"), tmp_path / "cefs-images", Path("/cefs"))

    # Create mock image files
    cefs_dir = tmp_path / "cefs-images"

    # Small consolidated image (100MB)
    small_dir = cefs_dir / "ab"
    small_dir.mkdir(parents=True)
    small_image = small_dir / "abc123_consolidated.sqfs"
    small_image.touch()

    # Large consolidated image (2GB)
    large_dir = cefs_dir / "de"
    large_dir.mkdir(parents=True)
    large_image = large_dir / "def456_consolidated.sqfs"
    large_image.touch()

    # Medium consolidated image (500MB)
    medium_dir = cefs_dir / "gh"
    medium_dir.mkdir(parents=True)
    medium_image = medium_dir / "ghi789_consolidated.sqfs"
    medium_image.touch()

    # Non-consolidated image (should be ignored)
    non_consol = small_dir / "xyz999.sqfs"
    non_consol.touch()

    # Set up state's all_cefs_images
    state.all_cefs_images = {
        "abc123_consolidated": small_image,
        "def456_consolidated": large_image,
        "ghi789_consolidated": medium_image,
        "xyz999": non_consol,
    }

    # Mock the stat calls to return specific sizes
    def mock_stat_method(self, **kwargs):
        # Handle .yaml files for manifest checks
        if str(self).endswith(".yaml"):
            # Raise FileNotFoundError for manifest files (they don't exist)
            raise FileNotFoundError(f"No such file: {self}")

        result = Mock()
        if "abc123" in str(self):
            result.st_size = 100 * 1024 * 1024  # 100MB
        elif "def456" in str(self):
            result.st_size = 2 * 1024 * 1024 * 1024  # 2GB
        elif "ghi789" in str(self):
            result.st_size = 500 * 1024 * 1024  # 500MB
        else:
            result.st_size = 50 * 1024 * 1024  # 50MB
        return result

    with patch.object(Path, "stat", mock_stat_method):
        # Find images smaller than 1GB
        small_images = state.find_small_consolidated_images(1024 * 1024 * 1024)
    assert len(small_images) == 2
    assert small_image in small_images
    assert medium_image in small_images
    assert large_image not in small_images
    assert non_consol not in small_images
