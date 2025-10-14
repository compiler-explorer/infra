#!/usr/bin/env python3
"""Tests for CEFS paths module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from lib.cefs.paths import (
    CEFSPaths,
    describe_cefs_image,
    get_cefs_image_path,
    get_cefs_mount_path,
    get_cefs_paths,
    get_current_symlink_targets,
    get_extraction_path_from_symlink,
    glob_with_depth,
    parse_cefs_target,
)


def test_get_cefs_image_path_with_filename():
    image_dir = Path("/efs/cefs-images")
    filename = "9da642f654bc890a12345678_gcc-15.1.0.sqfs"

    result = get_cefs_image_path(image_dir, filename)
    expected = Path("/efs/cefs-images/9d/9da642f654bc890a12345678_gcc-15.1.0.sqfs")

    assert result == expected


def test_get_cefs_mount_path_with_filename():
    filename = "9da642f654bc890a12345678_gcc-15.1.0.sqfs"

    result = get_cefs_mount_path(Path("/cefs"), filename)
    expected = Path("/cefs/9d/9da642f654bc890a12345678_gcc-15.1.0")

    assert result == expected


def test_parse_cefs_target_variations(tmp_path):
    cefs_image_dir = tmp_path / "cefs-images"
    mount_point = Path("/cefs")

    test_cases = [
        # (cefs_target, filename_to_create, expected_is_consolidated)
        ("/cefs/9d/9da642f654bc890a12345678", "9da642f654bc890a12345678_gcc-15.1.0.sqfs", False),
        ("/cefs/ab/abcdef1234567890abcdef12/gcc-4.5", "abcdef1234567890abcdef12_consolidated.sqfs", True),
    ]

    for cefs_target_str, filename, expected_consolidated in test_cases:
        cefs_target = Path(cefs_target_str)
        mount_parts_len = len(mount_point.parts)
        hash_prefix = cefs_target.parts[mount_parts_len]

        subdir = cefs_image_dir / hash_prefix
        subdir.mkdir(parents=True, exist_ok=True)
        image_file = subdir / filename
        image_file.touch()

        image_path, is_consolidated = parse_cefs_target(cefs_target, cefs_image_dir, mount_point)

        assert image_path == image_file
        assert is_consolidated == expected_consolidated


def test_get_extraction_path_from_symlink():
    mount_point = Path("/cefs")
    test_cases = [
        (Path("/cefs/ab/abcdef1234567890abcdef12"), None),
        (Path("/cefs/ab/abcdef1234567890abcdef12/content"), Path("content")),
        (Path("/cefs/ab/abcdef1234567890abcdef12/gcc-4.5"), Path("gcc-4.5")),
        (Path("/cefs/ab/abcdef1234567890abcdef12/libs/boost"), Path("libs/boost")),
        (Path("/cefs/cd/cdef1234567890123456789/deep/nested/path"), Path("deep/nested/path")),
    ]

    for symlink_target, expected in test_cases:
        result = get_extraction_path_from_symlink(symlink_target, mount_point)
        assert result == expected


def test_get_cefs_paths():
    image_dir = Path("/efs/cefs-images")
    mount_point = Path("/cefs")
    filename = "9da642f654bc890a12345678_gcc-15.1.0.sqfs"

    result = get_cefs_paths(image_dir, mount_point, filename)

    # Verify the result is a CEFSPaths object
    assert isinstance(result, CEFSPaths)

    # Verify the paths are correct
    expected_image_path = Path("/efs/cefs-images/9d/9da642f654bc890a12345678_gcc-15.1.0.sqfs")
    expected_mount_path = Path("/cefs/9d/9da642f654bc890a12345678_gcc-15.1.0")

    assert result.image_path == expected_image_path
    assert result.mount_path == expected_mount_path


# CEFS Path Parsing Tests


def test_parse_cefs_target_with_real_filesystem(tmp_path):
    cefs_image_dir = tmp_path / "cefs-images"
    mount_point = Path("/cefs")

    test_cases = [
        # (cefs_target, filename_to_create, expected_is_consolidated, description)
        (
            "/cefs/9d/9da642f6a4675f8305f992c02fd9cd019555cbfc2f00c4ba6f8110759aba43f9",
            "9da642f6a4675f8305f992c02fd9cd019555cbfc2f00c4ba6f8110759aba43f9_some_suffix.sqfs",
            False,
            "hierarchical format",
        ),
        (
            "/cefs/ab/abcdef123456789/gcc-4.5.4",
            "abcdef123456789_consolidated.sqfs",
            True,
            "consolidated format",
        ),
        (
            "/cefs/cd/cdef456789abc/some-lib/v1.2/bin",
            "cdef456789abc_consolidated.sqfs",
            True,
            "deeply nested consolidated",
        ),
        (
            "/cefs/9d/9da642f6a4675f8305f992c02fd9cd019555cbfc2f00c4ba6f8110759aba43f9",
            "9da642f6a4675f8305f992c02fd9cd019555cbfc2f00c4ba6f8110759aba43f9_gcc-assertions.sqfs",
            False,
            "gcc-assertions example",
        ),
    ]

    for cefs_target_str, filename, expected_consolidated, description in test_cases:
        cefs_target = Path(cefs_target_str)
        mount_parts_len = len(mount_point.parts)
        hash_prefix = cefs_target.parts[mount_parts_len][:2]  # Get first 2 chars of hash

        subdir = cefs_image_dir / hash_prefix
        subdir.mkdir(parents=True, exist_ok=True)
        image_file = subdir / filename
        image_file.touch()

        image_path, is_consolidated = parse_cefs_target(cefs_target, cefs_image_dir, mount_point)

        assert image_path == image_file, f"Failed for {description}"
        assert is_consolidated == expected_consolidated, f"Failed for {description}"


def test_parse_cefs_target_errors(tmp_path):
    cefs_image_dir = tmp_path / "cefs-images"
    mount_point = Path("/cefs")

    # Test invalid format with too few components
    with pytest.raises(ValueError, match="Invalid CEFS target format"):
        parse_cefs_target(Path("/cefs/9d"), cefs_image_dir, mount_point)

    # Test invalid format with wrong prefix
    with pytest.raises(ValueError, match="CEFS target must start with"):
        parse_cefs_target(Path("/invalid/9d/hash123"), cefs_image_dir, mount_point)

    # Test when no matching image file exists
    cefs_image_dir.mkdir(parents=True, exist_ok=True)
    with pytest.raises(ValueError, match="No CEFS image found"):
        parse_cefs_target(Path("/cefs/ab/abc123"), cefs_image_dir, mount_point)


def test_parse_cefs_target_with_custom_mount_point(tmp_path):
    """Test that parse_cefs_target works with custom mount points."""
    cefs_image_dir = tmp_path / "cefs-images"
    custom_mount = Path("/custom/mount")

    # Create test image
    hash_prefix = "9d"
    hash_val = "9da642f654bc890a12345678"
    filename = f"{hash_val}_test.sqfs"

    subdir = cefs_image_dir / hash_prefix
    subdir.mkdir(parents=True, exist_ok=True)
    image_file = subdir / filename
    image_file.touch()

    # Test with custom mount point
    cefs_target = custom_mount / hash_prefix / hash_val
    image_path, is_consolidated = parse_cefs_target(cefs_target, cefs_image_dir, custom_mount)

    assert image_path == image_file
    assert is_consolidated is False

    # Test consolidated with custom mount
    cefs_target_consolidated = custom_mount / hash_prefix / hash_val / "subdir"
    image_path, is_consolidated = parse_cefs_target(cefs_target_consolidated, cefs_image_dir, custom_mount)

    assert image_path == image_file
    assert is_consolidated is True


def test_get_extraction_path_with_custom_mount():
    """Test extraction path calculation with custom mount points."""
    custom_mount = Path("/test/cefs")

    test_cases = [
        (custom_mount / "ab" / "abcd1234", None),
        (custom_mount / "ab" / "abcd1234" / "content", Path("content")),
        (custom_mount / "ab" / "abcd1234" / "deep" / "path", Path("deep/path")),
    ]

    for symlink_target, expected in test_cases:
        result = get_extraction_path_from_symlink(symlink_target, custom_mount)
        assert result == expected


# CEFS Image Description Tests


def test_describe_cefs_image_with_real_filesystem(tmp_path):
    # Create a mock CEFS mount structure
    cefs_mount = tmp_path / "cefs"
    image_dir = cefs_mount / "ab" / "abc123"
    image_dir.mkdir(parents=True)

    # Create some test entries in the image
    (image_dir / "compilers_c++_x86_gcc_11.1.0").mkdir()
    (image_dir / "compilers_c++_x86_gcc_11.2.0").mkdir()
    (image_dir / "boost-1.82").mkdir()

    # Test the actual function (it uses get_cefs_mount_path internally)
    # We need to mock get_cefs_mount_path to return our test directory
    with patch("lib.cefs.paths.get_cefs_mount_path") as mock_get_mount:
        mock_get_mount.return_value = image_dir
        result = describe_cefs_image("abc123", cefs_mount)

    # Should list all directories we created
    assert sorted(result) == ["boost-1.82", "compilers_c++_x86_gcc_11.1.0", "compilers_c++_x86_gcc_11.2.0"]
    mock_get_mount.assert_called_once_with(cefs_mount, "abc123")


def test_describe_cefs_image_empty_directory(tmp_path):
    cefs_mount = tmp_path / "cefs"
    image_dir = cefs_mount / "de" / "def456"
    image_dir.mkdir(parents=True)

    with patch("lib.cefs.paths.get_cefs_mount_path") as mock_get_mount:
        mock_get_mount.return_value = image_dir
        result = describe_cefs_image("def456", cefs_mount)

    assert result == []


def test_describe_cefs_image_nonexistent_directory(tmp_path):
    cefs_mount = tmp_path / "cefs"
    # Don't create the directory - it doesn't exist
    nonexistent_dir = cefs_mount / "gh" / "ghi789"

    with patch("lib.cefs.paths.get_cefs_mount_path") as mock_get_mount:
        mock_get_mount.return_value = nonexistent_dir
        result = describe_cefs_image("ghi789", cefs_mount)

    # Should return empty list when directory doesn't exist (OSError)
    assert result == []


# CEFS State Tests


def test_get_current_symlink_targets(tmp_path):
    """Test get_current_symlink_targets function."""
    # Test with existing symlink at main path
    gcc_path = tmp_path / "gcc"
    gcc_path.symlink_to("/cefs/ab/abc123_consolidated/gcc")

    targets = get_current_symlink_targets(gcc_path)
    assert len(targets) == 1
    assert targets[0] == Path("/cefs/ab/abc123_consolidated/gcc")

    # Test with both main and .bak symlinks
    clang_path = tmp_path / "clang"
    clang_bak_path = tmp_path / "clang.bak"
    clang_path.symlink_to("/cefs/cd/def456_clang_new")
    clang_bak_path.symlink_to("/cefs/cd/def456_clang_old")

    targets2 = get_current_symlink_targets(clang_path)
    assert len(targets2) == 2
    assert Path("/cefs/cd/def456_clang_new") in targets2
    assert Path("/cefs/cd/def456_clang_old") in targets2

    # Test with only .bak symlink
    rust_path = tmp_path / "rust"
    rust_bak_path = tmp_path / "rust.bak"
    rust_bak_path.symlink_to("/cefs/ef/ghi789_rust")

    targets3 = get_current_symlink_targets(rust_path)
    assert len(targets3) == 1
    assert targets3[0] == Path("/cefs/ef/ghi789_rust")

    # Test with non-existent paths
    nonexistent_path = tmp_path / "nonexistent"
    targets4 = get_current_symlink_targets(nonexistent_path)
    assert targets4 == []


# Tests for glob_with_depth


def test_glob_with_depth_basic(tmp_path):
    """Test glob_with_depth finds files at various depths."""
    # Create test directory structure
    (tmp_path / "file1.txt").touch()
    (tmp_path / "dir1").mkdir()
    (tmp_path / "dir1" / "file2.txt").touch()
    (tmp_path / "dir1" / "dir2").mkdir()
    (tmp_path / "dir1" / "dir2" / "file3.txt").touch()
    (tmp_path / "dir1" / "dir2" / "file4.log").touch()

    # Test with max_depth=0 (current directory only)
    results = list(glob_with_depth(tmp_path, "*.txt", max_depth=0))
    assert len(results) == 1
    assert tmp_path / "file1.txt" in results

    # Test with max_depth=1 (current + one level down)
    results = list(glob_with_depth(tmp_path, "*.txt", max_depth=1))
    assert len(results) == 2
    assert tmp_path / "file1.txt" in results
    assert tmp_path / "dir1" / "file2.txt" in results

    # Test with max_depth=2 (all txt files in this structure)
    results = list(glob_with_depth(tmp_path, "*.txt", max_depth=2))
    assert len(results) == 3
    assert tmp_path / "file1.txt" in results
    assert tmp_path / "dir1" / "file2.txt" in results
    assert tmp_path / "dir1" / "dir2" / "file3.txt" in results


def test_glob_with_depth_all_files(tmp_path):
    """Test glob_with_depth with pattern '*' to find all files and directories."""
    # Create test structure
    (tmp_path / "file1.txt").touch()
    dir1 = tmp_path / "dir1"
    dir1.mkdir()
    (dir1 / "file2.txt").touch()

    # Test finding all items at depth 0
    results = list(glob_with_depth(tmp_path, "*", max_depth=0))
    assert len(results) == 2  # file1.txt and dir1
    assert tmp_path / "file1.txt" in results
    assert dir1 in results

    # Test finding all items at depth 1
    results = list(glob_with_depth(tmp_path, "*", max_depth=1))
    assert len(results) == 3  # file1.txt, dir1, and dir1/file2.txt
    assert tmp_path / "file1.txt" in results
    assert dir1 in results
    assert dir1 / "file2.txt" in results


def test_glob_with_depth_unlimited(tmp_path):
    """Test glob_with_depth with unlimited depth."""
    # Create deep structure
    deep_dir = tmp_path / "a" / "b" / "c" / "d"
    deep_dir.mkdir(parents=True)
    (deep_dir / "deep.txt").touch()
    (tmp_path / "shallow.txt").touch()

    # Test unlimited depth
    results = list(glob_with_depth(tmp_path, "*.txt", max_depth=None))
    assert len(results) == 2
    assert tmp_path / "shallow.txt" in results
    assert deep_dir / "deep.txt" in results


def test_glob_with_depth_no_matches(tmp_path):
    """Test glob_with_depth when no files match the pattern."""
    (tmp_path / "file.txt").touch()
    (tmp_path / "file.log").touch()

    # Search for non-existent pattern
    results = list(glob_with_depth(tmp_path, "*.bak", max_depth=2))
    assert results == []


def test_glob_with_depth_symlinks(tmp_path):
    """Test glob_with_depth behavior with symlinks."""
    # Create files and symlinks
    real_file = tmp_path / "real.txt"
    real_file.touch()

    link_file = tmp_path / "link.txt"
    link_file.symlink_to(real_file)

    # Both real file and symlink should be found
    results = list(glob_with_depth(tmp_path, "*.txt", max_depth=0))
    assert len(results) == 2
    assert real_file in results
    assert link_file in results


def test_glob_with_depth_does_not_follow_symlink_dirs(tmp_path):
    """CEFS fsck must not report .bak files inside CEFS-mounted images."""
    # Create a real directory with a .bak file inside
    real_dir = tmp_path / "real_dir"
    real_dir.mkdir()
    bak_file_in_real = real_dir / "file.bak"
    bak_file_in_real.touch()

    # Create a symlink directory pointing to real_dir
    symlink_dir = tmp_path / "symlink_dir"
    symlink_dir.symlink_to(real_dir)

    # Also put a .bak file inside the symlinked directory
    # (simulating a CEFS mount with internal .bak files)
    internal_bak = real_dir / "internal.bak"
    internal_bak.touch()

    # Create a .bak file at the root level
    root_bak = tmp_path / "root.bak"
    root_bak.touch()

    # Search for .bak files with depth limit
    results = list(glob_with_depth(tmp_path, "*.bak", max_depth=2))

    # Should find:
    # - root.bak at the root
    # - file.bak and internal.bak in real_dir
    # Should NOT find files through symlink_dir (would be duplicates)
    assert root_bak in results
    assert bak_file_in_real in results
    assert internal_bak in results

    # Importantly, we should not get duplicates through the symlink
    # (if we followed symlinks, we'd get the files twice)
    assert len(results) == 3

    # Verify that symlink_dir itself can be found if it matches pattern
    symlink_bak_dir = tmp_path / "dir.bak"
    symlink_bak_dir.symlink_to(real_dir)

    results2 = list(glob_with_depth(tmp_path, "*.bak", max_depth=0))
    # Should find root.bak and dir.bak (the symlink directory itself)
    assert len(results2) == 2
    assert root_bak in results2
    assert symlink_bak_dir in results2
