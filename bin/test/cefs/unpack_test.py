#!/usr/bin/env python3
"""Tests for CEFS unpack and repack operations."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from lib.cefs.unpack import repack_cefs_item, unpack_cefs_item
from lib.config import SquashfsConfig


@pytest.fixture
def squashfs_config():
    """Create a test squashfs config."""
    return SquashfsConfig(
        mksquashfs_path="/usr/bin/mksquashfs",
        unsquashfs_path="/usr/bin/unsquashfs",
        compression="zstd",
        compression_level=15,
    )


@pytest.fixture
def mock_paths(tmp_path):
    """Create mock paths for testing."""
    return {
        "nfs_path": tmp_path / "gcc-12.3.0",
        "cefs_image_dir": tmp_path / "cefs-images",
        "mount_point": Path("/cefs"),
        "local_temp_dir": tmp_path / "temp",
    }


@patch("lib.cefs.unpack.extract_squashfs_relocating_subdir")
@patch("lib.cefs.unpack.parse_cefs_target")
def test_unpack_simple_cefs_image(mock_parse, mock_extract, tmp_path, squashfs_config, mock_paths):
    """Test unpacking a simple (non-consolidated) CEFS image."""
    nfs_path = mock_paths["nfs_path"]
    cefs_image_path = mock_paths["cefs_image_dir"] / "ab" / "abc123_gcc.sqfs"
    cefs_image_path.parent.mkdir(parents=True, exist_ok=True)
    cefs_image_path.touch()

    # Create symlink pointing to CEFS
    nfs_path.symlink_to("/cefs/ab/abc123")

    # Mock parse_cefs_target to return the image path and indicate not consolidated
    mock_parse.return_value = (cefs_image_path, False)

    # Mock extract to just create the temp directory
    def mock_extract_impl(config, image_path, output_dir, extract_path):
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "bin").mkdir()
        (output_dir / "bin" / "gcc").touch()

    mock_extract.side_effect = mock_extract_impl

    result = unpack_cefs_item(
        "compilers/c++/x86/gcc 12.3.0",
        nfs_path,
        mock_paths["cefs_image_dir"],
        mock_paths["mount_point"],
        squashfs_config,
        defer_cleanup=False,
        dry_run=False,
    )

    assert result is True
    assert nfs_path.is_dir()  # Should now be a directory
    assert not nfs_path.is_symlink()
    backup_path = nfs_path.with_name(nfs_path.name + ".bak")
    assert backup_path.is_symlink()  # Old symlink saved as .bak
    assert (nfs_path / "bin" / "gcc").exists()

    # Verify extract was called
    mock_extract.assert_called_once()
    args = mock_extract.call_args[0]
    assert args[1] == cefs_image_path
    assert args[3] is None  # extract_path should be None for simple images


@patch("lib.cefs.unpack.extract_squashfs_relocating_subdir")
@patch("lib.cefs.unpack.parse_cefs_target")
def test_unpack_consolidated_image(mock_parse, mock_extract, tmp_path, squashfs_config, mock_paths):
    """Test unpacking from a consolidated CEFS image (extracts only the subdir)."""
    nfs_path = mock_paths["nfs_path"]
    cefs_image_path = mock_paths["cefs_image_dir"] / "ab" / "abc123_consolidated.sqfs"
    cefs_image_path.parent.mkdir(parents=True, exist_ok=True)
    cefs_image_path.touch()

    # Create symlink pointing to CEFS with subdirectory (consolidated)
    nfs_path.symlink_to("/cefs/ab/abc123/gcc-12.3.0")

    # Mock parse_cefs_target to return the image path and indicate consolidated
    mock_parse.return_value = (cefs_image_path, True)

    # Mock extract_squashfs_relocating_subdir to just create the directory with contents
    # The helper already handles the nested subdirectory extraction logic
    def mock_extract_impl(config, image_path, output_dir, extract_path):
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "bin").mkdir()
        (output_dir / "bin" / "gcc").touch()

    mock_extract.side_effect = mock_extract_impl

    result = unpack_cefs_item(
        "compilers/c++/x86/gcc 12.3.0",
        nfs_path,
        mock_paths["cefs_image_dir"],
        mock_paths["mount_point"],
        squashfs_config,
        defer_cleanup=False,
        dry_run=False,
    )

    assert result is True
    assert nfs_path.is_dir()

    # Verify extract was called with the subdirectory path
    mock_extract.assert_called_once()
    args = mock_extract.call_args[0]
    assert args[1] == cefs_image_path
    assert args[3] == Path("gcc-12.3.0")  # Should extract only this subdir

    # Verify the contents are directly in nfs_path, not nested in a subdirectory
    assert (nfs_path / "bin" / "gcc").exists()
    assert not (nfs_path / "gcc-12.3.0").exists()  # Should NOT have the nested subdir


def test_unpack_not_a_symlink(tmp_path, squashfs_config, mock_paths):
    """Test that unpacking a non-symlink raises an error."""
    nfs_path = mock_paths["nfs_path"]
    nfs_path.mkdir()  # Create as directory, not symlink

    with pytest.raises(RuntimeError, match="not a symlink"):
        unpack_cefs_item(
            "compilers/c++/x86/gcc 12.3.0",
            nfs_path,
            mock_paths["cefs_image_dir"],
            mock_paths["mount_point"],
            squashfs_config,
            defer_cleanup=False,
            dry_run=False,
        )


@patch("lib.cefs.unpack.parse_cefs_target")
def test_unpack_missing_image(mock_parse, tmp_path, squashfs_config, mock_paths):
    """Test that unpacking when the CEFS image is missing raises an error."""
    nfs_path = mock_paths["nfs_path"]
    cefs_image_path = mock_paths["cefs_image_dir"] / "ab" / "abc123_gcc.sqfs"
    # Don't create the actual image file

    nfs_path.symlink_to("/cefs/ab/abc123")
    mock_parse.return_value = (cefs_image_path, False)

    with pytest.raises(RuntimeError, match="CEFS image not found"):
        unpack_cefs_item(
            "compilers/c++/x86/gcc 12.3.0",
            nfs_path,
            mock_paths["cefs_image_dir"],
            mock_paths["mount_point"],
            squashfs_config,
            defer_cleanup=False,
            dry_run=False,
        )


@patch("lib.cefs.unpack.extract_squashfs_relocating_subdir")
@patch("lib.cefs.unpack.parse_cefs_target")
def test_unpack_with_defer_cleanup(mock_parse, mock_extract, tmp_path, squashfs_config, mock_paths):
    """Test unpacking with defer_cleanup creates .DELETE_ME instead of deleting old .bak."""
    nfs_path = mock_paths["nfs_path"]
    cefs_image_path = mock_paths["cefs_image_dir"] / "ab" / "abc123_gcc.sqfs"
    cefs_image_path.parent.mkdir(parents=True, exist_ok=True)
    cefs_image_path.touch()

    # Create symlink and old .bak
    nfs_path.symlink_to("/cefs/ab/abc123")
    old_backup = nfs_path.with_name(nfs_path.name + ".bak")
    old_backup.symlink_to("/cefs/cd/old_hash")

    mock_parse.return_value = (cefs_image_path, False)

    def mock_extract_impl(config, image_path, output_dir, extract_path):
        output_dir.mkdir(parents=True, exist_ok=True)

    mock_extract.side_effect = mock_extract_impl

    result = unpack_cefs_item(
        "compilers/c++/x86/gcc 12.3.0",
        nfs_path,
        mock_paths["cefs_image_dir"],
        mock_paths["mount_point"],
        squashfs_config,
        defer_cleanup=True,
        dry_run=False,
    )

    assert result is True

    # Old .bak should be renamed to .DELETE_ME_<timestamp>, not deleted
    delete_me_files = list(nfs_path.parent.glob("*.DELETE_ME_*"))
    assert len(delete_me_files) == 1
    assert not old_backup.exists()


def test_unpack_dry_run(tmp_path, squashfs_config, mock_paths):
    """Test that dry run doesn't actually unpack anything."""
    nfs_path = mock_paths["nfs_path"]
    cefs_image_path = mock_paths["cefs_image_dir"] / "ab" / "abc123_gcc.sqfs"
    cefs_image_path.parent.mkdir(parents=True, exist_ok=True)
    cefs_image_path.touch()

    nfs_path.symlink_to("/cefs/ab/abc123")

    with patch("lib.cefs.unpack.parse_cefs_target") as mock_parse:
        mock_parse.return_value = (cefs_image_path, False)

        result = unpack_cefs_item(
            "compilers/c++/x86/gcc 12.3.0",
            nfs_path,
            mock_paths["cefs_image_dir"],
            mock_paths["mount_point"],
            squashfs_config,
            defer_cleanup=False,
            dry_run=True,
        )

    assert result is True
    assert nfs_path.is_symlink()  # Should still be a symlink
    assert not (nfs_path.with_name(nfs_path.name + ".bak")).exists()


@patch("lib.cefs.unpack.create_squashfs_image")
@patch("lib.cefs.unpack.deploy_to_cefs_transactional")
@patch("lib.cefs.unpack.backup_and_symlink")
@patch("lib.cefs.unpack.get_cefs_paths")
@patch("lib.cefs.unpack.get_cefs_filename_for_image")
def test_repack_directory(
    mock_get_filename,
    mock_get_paths,
    mock_backup_symlink,
    mock_deploy,
    mock_create,
    tmp_path,
    squashfs_config,
    mock_paths,
):
    """Test repacking a directory into a new CEFS image."""
    nfs_path = mock_paths["nfs_path"]
    nfs_path.mkdir()
    (nfs_path / "bin").mkdir()
    (nfs_path / "bin" / "gcc").touch()

    # Mock the CEFS paths
    mock_cefs_paths = Mock()
    mock_cefs_paths.image_path = mock_paths["cefs_image_dir"] / "de" / "def456_gcc.sqfs"
    mock_cefs_paths.mount_path = Path("/cefs/de/def456")
    mock_get_paths.return_value = mock_cefs_paths
    mock_get_filename.return_value = "def456_gcc.sqfs"

    # Mock deploy context manager
    mock_deploy.return_value.__enter__ = Mock(return_value=mock_cefs_paths.image_path)
    mock_deploy.return_value.__exit__ = Mock(return_value=False)

    result = repack_cefs_item(
        "compilers/c++/x86/gcc 12.3.0",
        nfs_path,
        mock_paths["cefs_image_dir"],
        mock_paths["mount_point"],
        squashfs_config,
        mock_paths["local_temp_dir"],
        defer_cleanup=False,
        dry_run=False,
    )

    assert result is True

    # Verify squashfs image was created
    mock_create.assert_called_once()
    create_args = mock_create.call_args[0]
    assert create_args[1] == nfs_path  # Source directory

    # Verify backup_and_symlink was called
    mock_backup_symlink.assert_called_once()
    backup_args = mock_backup_symlink.call_args[0]
    assert backup_args[0] == nfs_path
    assert backup_args[1] == mock_cefs_paths.mount_path


def test_repack_not_a_directory(tmp_path, squashfs_config, mock_paths):
    """Test that repacking a non-directory raises an error."""
    nfs_path = mock_paths["nfs_path"]
    nfs_path.touch()  # Create as file

    with pytest.raises(RuntimeError, match="not a directory"):
        repack_cefs_item(
            "compilers/c++/x86/gcc 12.3.0",
            nfs_path,
            mock_paths["cefs_image_dir"],
            mock_paths["mount_point"],
            squashfs_config,
            mock_paths["local_temp_dir"],
            defer_cleanup=False,
            dry_run=False,
        )


def test_repack_symlink(tmp_path, squashfs_config, mock_paths):
    """Test that repacking a symlink raises an error."""
    nfs_path = mock_paths["nfs_path"]
    nfs_path.symlink_to("/cefs/ab/abc123")

    with pytest.raises(RuntimeError, match="is a symlink"):
        repack_cefs_item(
            "compilers/c++/x86/gcc 12.3.0",
            nfs_path,
            mock_paths["cefs_image_dir"],
            mock_paths["mount_point"],
            squashfs_config,
            mock_paths["local_temp_dir"],
            defer_cleanup=False,
            dry_run=False,
        )


def test_repack_dry_run(tmp_path, squashfs_config, mock_paths):
    """Test that dry run doesn't actually repack anything."""
    nfs_path = mock_paths["nfs_path"]
    nfs_path.mkdir()

    result = repack_cefs_item(
        "compilers/c++/x86/gcc 12.3.0",
        nfs_path,
        mock_paths["cefs_image_dir"],
        mock_paths["mount_point"],
        squashfs_config,
        mock_paths["local_temp_dir"],
        defer_cleanup=False,
        dry_run=True,
    )

    assert result is True
    assert nfs_path.is_dir()  # Should still be a directory


@patch("lib.cefs.unpack.create_squashfs_image")
@patch("lib.cefs.unpack.deploy_to_cefs_transactional")
@patch("lib.cefs.unpack.backup_and_symlink")
@patch("lib.cefs.unpack.get_cefs_paths")
@patch("lib.cefs.unpack.get_cefs_filename_for_image")
@patch("lib.cefs.unpack.extract_squashfs_relocating_subdir")
@patch("lib.cefs.unpack.parse_cefs_target")
def test_unpack_repack_roundtrip(
    mock_parse,
    mock_extract,
    mock_get_filename,
    mock_get_paths,
    mock_backup_symlink,
    mock_deploy,
    mock_create,
    tmp_path,
    squashfs_config,
    mock_paths,
):
    """Test unpacking, modifying, and repacking a CEFS image."""
    nfs_path = mock_paths["nfs_path"]
    original_image = mock_paths["cefs_image_dir"] / "ab" / "abc123_gcc.sqfs"
    original_image.parent.mkdir(parents=True, exist_ok=True)
    original_image.touch()

    # Step 1: Unpack
    nfs_path.symlink_to("/cefs/ab/abc123")
    mock_parse.return_value = (original_image, False)

    def mock_extract_impl(config, image_path, output_dir, extract_path):
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "bin").mkdir()
        (output_dir / "bin" / "gcc").touch()

    mock_extract.side_effect = mock_extract_impl

    unpack_result = unpack_cefs_item(
        "compilers/c++/x86/gcc 12.3.0",
        nfs_path,
        mock_paths["cefs_image_dir"],
        mock_paths["mount_point"],
        squashfs_config,
        defer_cleanup=False,
        dry_run=False,
    )

    assert unpack_result is True
    assert nfs_path.is_dir()

    # Step 2: Modify (simulate user changes)
    (nfs_path / "modified_file.txt").write_text("This file was added after unpacking")

    # Step 3: Repack
    mock_cefs_paths = Mock()
    mock_cefs_paths.image_path = mock_paths["cefs_image_dir"] / "de" / "def456_gcc.sqfs"
    mock_cefs_paths.mount_path = Path("/cefs/de/def456")
    mock_get_paths.return_value = mock_cefs_paths
    mock_get_filename.return_value = "def456_gcc.sqfs"
    mock_deploy.return_value.__enter__ = Mock(return_value=mock_cefs_paths.image_path)
    mock_deploy.return_value.__exit__ = Mock(return_value=False)

    repack_result = repack_cefs_item(
        "compilers/c++/x86/gcc 12.3.0",
        nfs_path,
        mock_paths["cefs_image_dir"],
        mock_paths["mount_point"],
        squashfs_config,
        mock_paths["local_temp_dir"],
        defer_cleanup=False,
        dry_run=False,
    )

    assert repack_result is True

    # Verify the squashfs image was created with the modified directory
    mock_create.assert_called_once()
    create_args = mock_create.call_args[0]
    assert create_args[1] == nfs_path  # Should include modified_file.txt
