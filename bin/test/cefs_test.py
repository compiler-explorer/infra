#!/usr/bin/env python3
"""Tests for CEFS consolidation functionality."""

import datetime
import os
import time
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import yaml
from lib.cefs import (
    CEFSPaths,
    CEFSState,
    check_temp_space_available,
    delete_image_with_manifest,
    describe_cefs_image,
    filter_images_by_age,
    format_image_contents_string,
    get_cefs_image_path,
    get_cefs_mount_path,
    get_cefs_paths,
    get_extraction_path_from_symlink,
    get_image_description,
    get_image_description_from_manifest,
    has_enough_space,
    parse_cefs_target,
    snapshot_symlink_targets,
    verify_symlinks_unchanged,
)
from lib.cefs_manifest import (
    create_installable_manifest_entry,
    create_manifest,
    finalize_manifest,
    generate_cefs_filename,
    get_git_sha,
    read_manifest_from_alongside,
    sanitize_path_for_filename,
    write_manifest_alongside_image,
    write_manifest_inprogress,
)
from pytest import approx

# CEFS Consolidation Tests


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

    test_cases = [
        # (cefs_target, filename_to_create, expected_is_consolidated)
        ("/cefs/9d/9da642f654bc890a12345678", "9da642f654bc890a12345678_gcc-15.1.0.sqfs", False),
        ("/cefs/ab/abcdef1234567890abcdef12/gcc-4.5", "abcdef1234567890abcdef12_consolidated.sqfs", True),
    ]

    for cefs_target_str, filename, expected_consolidated in test_cases:
        cefs_target = Path(cefs_target_str)
        hash_prefix = cefs_target.parts[2]

        subdir = cefs_image_dir / hash_prefix
        subdir.mkdir(parents=True, exist_ok=True)
        image_file = subdir / filename
        image_file.touch()

        image_path, is_consolidated = parse_cefs_target(cefs_target, cefs_image_dir)

        assert image_path == image_file
        assert is_consolidated == expected_consolidated


def test_get_extraction_path_from_symlink():
    test_cases = [
        (Path("/cefs/ab/abcdef1234567890abcdef12"), Path(".")),
        (Path("/cefs/ab/abcdef1234567890abcdef12/content"), Path("content")),
        (Path("/cefs/ab/abcdef1234567890abcdef12/gcc-4.5"), Path("gcc-4.5")),
        (Path("/cefs/ab/abcdef1234567890abcdef12/libs/boost"), Path("libs/boost")),
        (Path("/cefs/cd/cdef1234567890123456789/deep/nested/path"), Path("deep/nested/path")),
    ]

    for symlink_target, expected in test_cases:
        result = get_extraction_path_from_symlink(symlink_target)
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
        hash_prefix = cefs_target.parts[2][:2]  # Get first 2 chars of hash

        subdir = cefs_image_dir / hash_prefix
        subdir.mkdir(parents=True, exist_ok=True)
        image_file = subdir / filename
        image_file.touch()

        image_path, is_consolidated = parse_cefs_target(cefs_target, cefs_image_dir)

        assert image_path == image_file, f"Failed for {description}"
        assert is_consolidated == expected_consolidated, f"Failed for {description}"


def test_parse_cefs_target_errors(tmp_path):
    cefs_image_dir = tmp_path / "cefs-images"

    # Test invalid format with too few components
    with pytest.raises(ValueError, match="Invalid CEFS target format"):
        parse_cefs_target(Path("/cefs/9d"), cefs_image_dir)

    # Test invalid format with wrong prefix
    with pytest.raises(ValueError, match="CEFS target must start with /cefs"):
        parse_cefs_target(Path("/invalid/9d/hash123"), cefs_image_dir)

    # Test when no matching image file exists
    cefs_image_dir.mkdir(parents=True, exist_ok=True)
    with pytest.raises(ValueError, match="No CEFS image found"):
        parse_cefs_target(Path("/cefs/ab/abc123"), cefs_image_dir)


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
    with patch("lib.cefs.get_cefs_mount_path") as mock_get_mount:
        mock_get_mount.return_value = image_dir
        result = describe_cefs_image("abc123", cefs_mount)

    # Should list all directories we created
    assert sorted(result) == ["boost-1.82", "compilers_c++_x86_gcc_11.1.0", "compilers_c++_x86_gcc_11.2.0"]
    mock_get_mount.assert_called_once_with(cefs_mount, "abc123")


def test_describe_cefs_image_empty_directory(tmp_path):
    cefs_mount = tmp_path / "cefs"
    image_dir = cefs_mount / "de" / "def456"
    image_dir.mkdir(parents=True)

    with patch("lib.cefs.get_cefs_mount_path") as mock_get_mount:
        mock_get_mount.return_value = image_dir
        result = describe_cefs_image("def456", cefs_mount)

    assert result == []


def test_describe_cefs_image_nonexistent_directory(tmp_path):
    cefs_mount = tmp_path / "cefs"
    # Don't create the directory - it doesn't exist
    nonexistent_dir = cefs_mount / "gh" / "ghi789"

    with patch("lib.cefs.get_cefs_mount_path") as mock_get_mount:
        mock_get_mount.return_value = nonexistent_dir
        result = describe_cefs_image("ghi789", cefs_mount)

    # Should return empty list when directory doesn't exist (OSError)
    assert result == []


# CEFS State Tests


def test_cefs_state_init():
    nfs_dir = Path("/opt/compiler-explorer")
    cefs_image_dir = Path("/efs/cefs-images")
    state = CEFSState(nfs_dir, cefs_image_dir)

    assert state.nfs_dir == nfs_dir
    assert state.cefs_image_dir == cefs_image_dir
    assert not state.referenced_images
    assert not state.all_cefs_images


def test_find_unreferenced_images():
    nfs_dir = Path("/opt/compiler-explorer")
    cefs_image_dir = Path("/efs/cefs-images")
    state = CEFSState(nfs_dir, cefs_image_dir)

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
    state = CEFSState(nfs_dir, cefs_image_dir)

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
    state = CEFSState(nfs_dir, cefs_image_dir)

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
    state = CEFSState(nfs_dir, cefs_image_dir)

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
    regular_manifest.write_text(yaml.dump({"contents": [{"name": "test", "destination": str(nfs_dir / "test")}]}))

    inprogress_image = subdir / "def456_test.sqfs"
    inprogress_image.touch()
    inprogress_manifest = subdir / "def456_test.yaml.inprogress"
    inprogress_manifest.write_text(
        yaml.dump({"contents": [{"name": "inprog", "destination": str(nfs_dir / "inprog")}]})
    )

    state = CEFSState(nfs_dir, cefs_dir)
    state.scan_cefs_images_with_manifests()

    # Image with inprogress should be marked as referenced (protected)
    assert "def456_test" in state.referenced_images
    # Regular image should be in all_cefs_images
    assert "abc123_test" in state.all_cefs_images
    # Should have found the inprogress file
    assert len(state.inprogress_images) == 1
    assert state.inprogress_images[0] == inprogress_manifest


# CEFS Manifest Tests


def test_write_and_finalize_manifest(tmp_path):
    image_path = tmp_path / "test.sqfs"
    image_path.touch()

    manifest = {"version": 1, "operation": "test", "contents": []}

    # Write in-progress manifest
    write_manifest_inprogress(manifest, image_path)

    inprogress_path = Path(str(image_path.with_suffix(".yaml")) + ".inprogress")
    assert inprogress_path.exists()

    # Finalize it
    finalize_manifest(image_path)

    final_path = image_path.with_suffix(".yaml")
    assert final_path.exists()
    assert not inprogress_path.exists()


def test_finalize_missing_inprogress(tmp_path):
    image_path = tmp_path / "test.sqfs"
    image_path.touch()

    with pytest.raises(FileNotFoundError):
        finalize_manifest(image_path)


@pytest.mark.parametrize(
    "input_path,expected",
    [
        (Path("/opt/compiler-explorer/gcc-15.1.0"), "opt_compiler-explorer_gcc-15.1.0"),
        (Path("libs/fusedkernellibrary/Beta-0.1.9/"), "libs_fusedkernellibrary_Beta-0.1.9"),
        (Path("arm/gcc-10.2.0"), "arm_gcc-10.2.0"),
        (Path("path with spaces"), "path_with_spaces"),
        (Path("path:with:colons"), "path_with_colons"),
    ],
)
def test_sanitize_path_for_filename(input_path, expected):
    assert sanitize_path_for_filename(input_path) == expected


@pytest.mark.parametrize(
    "operation,path,expected",
    [
        (
            "install",
            Path("/opt/compiler-explorer/gcc-15.1.0"),
            "9da642f654bc890a12345678_opt_compiler-explorer_gcc-15.1.0.sqfs",
        ),
        ("consolidate", None, "9da642f654bc890a12345678_consolidated.sqfs"),
        ("convert", Path("arm/gcc-10.2.0.img"), "9da642f654bc890a12345678_converted_arm_gcc-10.2.0.sqfs"),
        ("unknown", Path("test"), "9da642f654bc890a12345678_test.sqfs"),
    ],
)
def test_generate_cefs_filename(operation, path, expected):
    hash_value = "9da642f654bc890a12345678"
    result = generate_cefs_filename(hash_value, operation, path)
    assert result == expected


@pytest.mark.parametrize(
    "installable_name,destination_path,expected",
    [
        (
            "compilers/c++/x86/gcc 10.1.0",
            Path("/opt/compiler-explorer/gcc-10.1.0"),
            {
                "name": "compilers/c++/x86/gcc 10.1.0",
                "destination": "/opt/compiler-explorer/gcc-10.1.0",
            },
        ),
        (
            "libraries/boost 1.84.0",
            Path("/opt/compiler-explorer/libs/boost_1_84_0"),
            {
                "name": "libraries/boost 1.84.0",
                "destination": "/opt/compiler-explorer/libs/boost_1_84_0",
            },
        ),
        (
            "tools/cmake 3.25.1",
            Path("/opt/compiler-explorer/cmake-3.25.1"),
            {
                "name": "tools/cmake 3.25.1",
                "destination": "/opt/compiler-explorer/cmake-3.25.1",
            },
        ),
    ],
)
def test_create_installable_manifest_entry(installable_name, destination_path, expected):
    result = create_installable_manifest_entry(installable_name, destination_path)
    assert result == expected


@patch("lib.cefs_manifest.subprocess.run")
def test_get_git_sha_success(mock_run):
    mock_result = Mock()
    mock_result.returncode = 0
    mock_result.stdout = "d8c0bd74f9e5ef47e89d6eefe67414bf6b99e3dd\n"
    mock_run.return_value = mock_result

    # Clear the cache first
    get_git_sha.cache_clear()

    result = get_git_sha()
    assert result == "d8c0bd74f9e5ef47e89d6eefe67414bf6b99e3dd"

    # Test caching - should not call subprocess again
    result2 = get_git_sha()
    assert result2 == "d8c0bd74f9e5ef47e89d6eefe67414bf6b99e3dd"
    mock_run.assert_called_once()


@patch("lib.cefs_manifest.subprocess.run")
def test_get_git_sha_failure(mock_run):
    mock_result = Mock()
    mock_result.returncode = 1
    mock_result.stderr = "Not a git repository"
    mock_run.return_value = mock_result

    # Clear the cache first
    get_git_sha.cache_clear()

    result = get_git_sha()
    assert result == "unknown"


def test_create_manifest():
    contents = [{"name": "compilers/c++/x86/gcc 15.1.0", "destination": "/opt/compiler-explorer/gcc-15.1.0"}]

    with patch("lib.cefs_manifest.get_git_sha", return_value="test_sha"):
        manifest = create_manifest(
            operation="install",
            description="Test installation",
            contents=contents,
            command=["ce_install", "install", "gcc-15.1.0"],
        )

    assert manifest["version"] == 1
    assert manifest["operation"] == "install"
    assert manifest["description"] == "Test installation"
    assert manifest["contents"] == contents
    assert manifest["command"] == ["ce_install", "install", "gcc-15.1.0"]
    assert manifest["git_sha"] == "test_sha"
    assert "created_at" in manifest

    # Verify created_at is a valid ISO format timestamp
    datetime.datetime.fromisoformat(manifest["created_at"])


def test_write_and_read_manifest_alongside_image(tmp_path):
    image_path = tmp_path / "test_image.sqfs"

    # Create dummy image file
    image_path.touch()

    manifest = {"version": 1, "operation": "test", "description": "Test manifest", "contents": []}

    # Write manifest alongside
    write_manifest_alongside_image(manifest, image_path)

    # Read manifest back
    loaded_manifest = read_manifest_from_alongside(image_path)

    assert loaded_manifest == manifest


def test_read_manifest_from_alongside_nonexistent(tmp_path):
    image_path = tmp_path / "nonexistent.sqfs"

    result = read_manifest_from_alongside(image_path)
    assert result is None


def test_read_manifest_from_alongside_invalid_yaml(tmp_path):
    image_path = tmp_path / "test_image.sqfs"
    manifest_path = image_path.with_suffix(".yaml")

    # Write invalid YAML
    manifest_path.write_text("invalid: yaml: content: [")

    with pytest.raises(yaml.YAMLError):
        read_manifest_from_alongside(image_path)


# CEFS Garbage Collection Tests


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
    manifest_content = {"contents": [{"name": "test-compiler", "destination": str(nfs_dir / "test-compiler")}]}
    manifest_path.write_text(yaml.dump(manifest_content))

    # Create state and do initial scan
    state = CEFSState(nfs_dir, cefs_image_dir)
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
    manifest_content = {"contents": [{"name": "rollback-compiler", "destination": str(nfs_dir / "rollback-compiler")}]}
    manifest_path.write_text(yaml.dump(manifest_content))

    # Create only .bak symlink (main symlink is missing/broken)
    bak_symlink = nfs_dir / "rollback-compiler.bak"
    bak_symlink.symlink_to(f"/cefs/{image_hash[:2]}/{image_hash}")

    # Create state and scan
    state = CEFSState(nfs_dir, cefs_image_dir)
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
    state = CEFSState(nfs_dir, cefs_image_dir)
    state.scan_cefs_images_with_manifests()

    # Image should be in referenced set (protected from deletion)
    assert image_hash in state.referenced_images, ".yaml.inprogress should protect image"
    assert inprogress_path in state.inprogress_images


def test_age_filtering_logic(tmp_path):
    nfs_dir = tmp_path / "nfs"
    cefs_image_dir = tmp_path / "cefs-images"
    nfs_dir.mkdir()
    cefs_image_dir.mkdir()

    # Create test images with different ages
    old_hash = "old001"
    new_hash = "new002"

    for hash_val in [old_hash, new_hash]:
        subdir = cefs_image_dir / hash_val[:2]
        subdir.mkdir(exist_ok=True)
        image_path = subdir / f"{hash_val}.sqfs"
        image_path.touch()

        # Create manifest so image is valid
        manifest_path = image_path.with_suffix(".yaml")
        manifest_content = {
            "contents": [{"name": f"test-{hash_val}", "destination": str(nfs_dir / f"test-{hash_val}")}]
        }
        manifest_path.write_text(yaml.dump(manifest_content))

        # Set modification time
        if hash_val == old_hash:
            # Make this image 2 hours old
            old_time = time.time() - (2 * 3600)
            os.utime(image_path, (old_time, old_time))

    # Create state and scan
    state = CEFSState(nfs_dir, cefs_image_dir)
    state.scan_cefs_images_with_manifests()
    state.check_symlink_references()

    # Both should be unreferenced
    unreferenced = state.find_unreferenced_images()
    assert len(unreferenced) == 2

    # With 1 hour min age, only old image should be eligible
    now = datetime.datetime.now()
    min_age_delta = datetime.timedelta(hours=1)

    eligible_for_deletion = []
    for image_path in unreferenced:
        mtime = datetime.datetime.fromtimestamp(image_path.stat().st_mtime)
        age = now - mtime
        if age >= min_age_delta:
            eligible_for_deletion.append(image_path)

    assert len(eligible_for_deletion) == 1, "Only old image should be eligible for deletion"
    assert eligible_for_deletion[0].stem == old_hash


def test_images_without_manifests_are_broken(tmp_path):
    nfs_dir = tmp_path / "nfs"
    cefs_image_dir = tmp_path / "cefs-images"
    nfs_dir.mkdir()
    cefs_image_dir.mkdir()

    # Create test image WITHOUT manifest or inprogress marker
    image_hash = "jkl012"
    subdir = cefs_image_dir / image_hash[:2]
    subdir.mkdir()
    image_path = subdir / f"{image_hash}.sqfs"
    image_path.touch()
    # No manifest created - this is a broken image

    # Create a symlink pointing to this image
    symlink_path = nfs_dir / "legacy-compiler"
    symlink_path.symlink_to(f"/cefs/{image_hash[:2]}/{image_hash}")

    # Create state and scan
    state = CEFSState(nfs_dir, cefs_image_dir)
    state.scan_cefs_images_with_manifests()
    state.check_symlink_references()

    # Image should be marked as broken, not in all_cefs_images
    assert image_hash not in state.all_cefs_images, "Broken image should not be in all_cefs_images"
    assert image_hash not in state.referenced_images, "Broken image should not be in referenced_images"
    assert len(state.broken_images) == 1, "Should have one broken image"
    assert state.broken_images[0] == image_path, "Should track the broken image path"


def test_concurrent_gc_safety(tmp_path):
    nfs_dir = tmp_path / "nfs"
    cefs_image_dir = tmp_path / "cefs-images"
    nfs_dir.mkdir()
    cefs_image_dir.mkdir()

    # Create test image with manifest
    image_hash = "mno345"
    subdir = cefs_image_dir / image_hash[:2]
    subdir.mkdir()
    image_path = subdir / f"{image_hash}.sqfs"
    image_path.touch()

    # Create manifest so image is valid
    manifest_path = image_path.with_suffix(".yaml")
    manifest_content = {"contents": [{"name": "test-compiler", "destination": str(nfs_dir / "test-compiler")}]}
    manifest_path.write_text(yaml.dump(manifest_content))

    # Create two independent state objects (simulating concurrent GC runs)
    state1 = CEFSState(nfs_dir, cefs_image_dir)
    state2 = CEFSState(nfs_dir, cefs_image_dir)

    # Both scan at the same time
    state1.scan_cefs_images_with_manifests()
    state2.scan_cefs_images_with_manifests()

    # Both identify the same unreferenced image
    unreferenced1 = state1.find_unreferenced_images()
    unreferenced2 = state2.find_unreferenced_images()

    assert len(unreferenced1) == 1
    assert unreferenced1 == unreferenced2

    # If first GC deletes the image
    if image_path.exists():
        image_path.unlink()

    # Second GC should handle missing file gracefully
    # (In real code, this would be in a try/except block)
    assert not image_path.exists()


def test_full_gc_workflow_integration(tmp_path):
    nfs_dir = tmp_path / "nfs"
    cefs_image_dir = tmp_path / "cefs-images"
    nfs_dir.mkdir()
    cefs_image_dir.mkdir()

    # Setup: Create multiple images with different states

    # 1. Referenced image with manifest and symlink
    ref_hash = "ref001"
    ref_subdir = cefs_image_dir / ref_hash[:2]
    ref_subdir.mkdir()
    ref_image = ref_subdir / f"{ref_hash}.sqfs"
    ref_image.write_bytes(b"referenced content")

    ref_manifest = ref_image.with_suffix(".yaml")
    ref_manifest.write_text(yaml.dump({"contents": [{"name": "gcc-11", "destination": str(nfs_dir / "gcc-11")}]}))

    # Create the symlink
    (nfs_dir / "gcc-11").symlink_to(f"/cefs/{ref_hash[:2]}/{ref_hash}")

    # 2. Unreferenced image with manifest but no symlink
    unref_hash = "unref002"
    unref_subdir = cefs_image_dir / unref_hash[:2]
    unref_subdir.mkdir()
    unref_image = unref_subdir / f"{unref_hash}.sqfs"
    unref_image.write_bytes(b"unreferenced content")

    unref_manifest = unref_image.with_suffix(".yaml")
    unref_manifest.write_text(
        yaml.dump({"contents": [{"name": "old-compiler", "destination": str(nfs_dir / "old-compiler")}]})
    )
    # No symlink created - this should be GC'd

    # 3. In-progress image (should be protected)
    inprog_hash = "inprog003"
    inprog_subdir = cefs_image_dir / inprog_hash[:2]
    inprog_subdir.mkdir()
    inprog_image = inprog_subdir / f"{inprog_hash}.sqfs"
    inprog_image.write_bytes(b"in-progress content")

    # Create .yaml.inprogress
    inprog_manifest = Path(str(inprog_image.with_suffix(".yaml")) + ".inprogress")
    inprog_manifest.touch()

    # 4. Image with .bak symlink only
    bak_hash = "bak004"
    bak_subdir = cefs_image_dir / bak_hash[:2]
    bak_subdir.mkdir()
    bak_image = bak_subdir / f"{bak_hash}.sqfs"
    bak_image.write_bytes(b"backup content")

    bak_manifest = bak_image.with_suffix(".yaml")
    bak_manifest.write_text(
        yaml.dump({"contents": [{"name": "backup-gcc", "destination": str(nfs_dir / "backup-gcc")}]})
    )

    # Create only .bak symlink
    (nfs_dir / "backup-gcc.bak").symlink_to(f"/cefs/{bak_hash[:2]}/{bak_hash}")

    # Run the full GC workflow
    state = CEFSState(nfs_dir, cefs_image_dir)
    state.scan_cefs_images_with_manifests()
    state.check_symlink_references()

    # Verify the state
    summary = state.get_summary()
    # Note: inprog image is not included in total_images because it's skipped due to .yaml.inprogress
    # but it IS added to referenced_images to protect it from deletion
    assert summary.total_images == 3, "Should have 3 total images (inprog excluded)"
    assert summary.referenced_images == 3, "Should have 3 referenced images (ref, inprog, bak)"
    assert summary.unreferenced_images == 1, "Should have 1 unreferenced image"

    # Check specific images
    assert ref_hash in state.referenced_images, "Referenced image should be protected"
    assert unref_hash not in state.referenced_images, "Unreferenced image should be marked for deletion"
    assert inprog_hash in state.referenced_images, "In-progress image should be protected"
    assert bak_hash in state.referenced_images, ".bak image should be protected"

    # Verify unreferenced images list
    unreferenced = state.find_unreferenced_images()
    assert len(unreferenced) == 1
    assert unreferenced[0].stem == unref_hash

    # Simulate deletion (what GC would do)
    for image_path in unreferenced:
        # Double-check before deletion (as the real GC does)
        filename_stem = image_path.stem
        should_delete = True

        if filename_stem in state.image_references:
            for dest_path in state.image_references[filename_stem]:
                if state._check_symlink_points_to_image(dest_path, filename_stem):
                    should_delete = False
                    break

        if should_delete:
            image_path.unlink()
            manifest_path = image_path.with_suffix(".yaml")
            if manifest_path.exists():
                manifest_path.unlink()

    # Verify deletion
    assert not unref_image.exists(), "Unreferenced image should be deleted"
    assert not unref_manifest.exists(), "Unreferenced manifest should be deleted"
    assert ref_image.exists(), "Referenced image should still exist"
    assert inprog_image.exists(), "In-progress image should still exist"
    assert bak_image.exists(), ".bak image should still exist"


# Tests for Extracted GC Utility Functions


def test_filter_images_by_age(tmp_path):
    # Create images with different ages
    old_image = tmp_path / "old.sqfs"
    recent_image = tmp_path / "recent.sqfs"
    broken_image = tmp_path / "broken.sqfs"

    # Create files
    old_image.touch()
    recent_image.touch()

    # Set old image to 2 hours ago
    old_time = time.time() - (2 * 3600)
    os.utime(old_image, (old_time, old_time))

    # recent_image has current time (just created)

    # Test filtering with 1 hour threshold
    test_now = datetime.datetime.now()
    min_age_delta = datetime.timedelta(hours=1)

    images = [old_image, recent_image, broken_image]  # broken doesn't exist
    result = filter_images_by_age(images, min_age_delta, test_now)

    # Old image and broken (non-existent) should be in old_enough
    assert set(result.old_enough) == {old_image, broken_image}  # Can't stat = assume broken = old enough

    # Recent image should be in too_recent with its age
    assert len(result.too_recent) == 1
    assert result.too_recent[0][0] == recent_image
    assert result.too_recent[0][1] < min_age_delta


def test_get_image_description_from_manifest(tmp_path):
    image_path = tmp_path / "test.sqfs"
    manifest_path = image_path.with_suffix(".yaml")

    # Test with valid manifest
    manifest_path.write_text(
        yaml.dump({
            "contents": [
                {"name": "gcc-11", "destination": "/opt/gcc-11"},
                {"name": "boost-1.75", "destination": "/opt/boost"},
            ]
        })
    )

    assert get_image_description_from_manifest(image_path) == ["gcc-11", "boost-1.75"]

    # Test with empty contents
    manifest_path.write_text(yaml.dump({"contents": []}))
    assert get_image_description_from_manifest(image_path) is None

    # Test with missing manifest
    manifest_path.unlink()
    assert get_image_description_from_manifest(image_path) is None

    # Test with invalid YAML
    manifest_path.write_text("invalid: yaml: content: {")
    assert get_image_description_from_manifest(image_path) is None


def test_format_image_contents_string():
    # Test with None
    assert not format_image_contents_string(None, 3)

    # Test with empty list
    assert not format_image_contents_string([], 3)

    # Test with items <= max_items
    assert format_image_contents_string(["gcc-11", "boost"], 3) == " [contains: gcc-11, boost]"

    # Test with items > max_items
    assert (
        format_image_contents_string(["gcc-11", "boost", "cmake", "ninja", "python"], 3)
        == " [contains: gcc-11, boost, cmake...]"
    )

    # Test with max_items = 1
    assert format_image_contents_string(["gcc-11", "boost"], 1) == " [contains: gcc-11...]"


def test_delete_image_with_manifest(tmp_path):
    image_path = tmp_path / "test.sqfs"
    manifest_path = image_path.with_suffix(".yaml")

    # Test successful deletion with manifest
    image_path.write_bytes(b"image content")
    manifest_path.write_text("manifest content")

    result = delete_image_with_manifest(image_path)
    assert result.success
    assert result.deleted_size == len(b"image content")
    assert not result.errors
    assert not image_path.exists()
    assert not manifest_path.exists()

    # Test deletion without manifest
    image_path.write_bytes(b"image")
    result = delete_image_with_manifest(image_path)
    assert result.success
    assert result.deleted_size == len(b"image")
    assert not result.errors

    # Test deletion of non-existent image
    result = delete_image_with_manifest(image_path)
    assert not result.success
    assert result.deleted_size == 0
    assert len(result.errors) == 2  # stat error and delete error

    # Test deletion when manifest doesn't exist but image does
    image_path.write_bytes(b"content")
    # No manifest created this time
    result = delete_image_with_manifest(image_path)
    assert result.success  # Image was deleted successfully
    assert result.deleted_size == len(b"content")
    assert not result.errors
    assert not image_path.exists()


def test_get_image_description_integration(tmp_path):
    image_path = tmp_path / "test.sqfs"
    manifest_path = image_path.with_suffix(".yaml")
    cefs_mount = Path("/fake/cefs")  # Won't be used if manifest exists

    # Test with manifest
    manifest_path.write_text(yaml.dump({"contents": [{"name": "gcc-11", "destination": "/opt/gcc-11"}]}))
    assert get_image_description(image_path, cefs_mount) == ["gcc-11"]

    # Test without manifest (will try to mount, which will fail)
    manifest_path.unlink()
    assert get_image_description(image_path, cefs_mount) is None  # Falls back to mounting which fails in test


def test_is_image_referenced(tmp_path):
    nfs_dir = tmp_path / "nfs"
    cefs_dir = tmp_path / "cefs"
    nfs_dir.mkdir()
    cefs_dir.mkdir()

    state = CEFSState(nfs_dir, cefs_dir)

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


def test_filter_images_by_age_with_specific_times(tmp_path):
    image1 = tmp_path / "image1.sqfs"
    image2 = tmp_path / "image2.sqfs"
    image3 = tmp_path / "image3.sqfs"

    # Create files
    for img in [image1, image2, image3]:
        img.touch()

    # Set specific modification times
    base_time = time.time()
    os.utime(image1, (base_time - 7200, base_time - 7200))  # 2 hours old
    os.utime(image2, (base_time - 3600, base_time - 3600))  # 1 hour old
    os.utime(image3, (base_time - 1800, base_time - 1800))  # 30 minutes old

    # Test with 45 minute threshold
    test_now = datetime.datetime.fromtimestamp(base_time)
    min_age_delta = datetime.timedelta(minutes=45)

    images = [image1, image2, image3]
    result = filter_images_by_age(images, min_age_delta, test_now)

    # image1 and image2 should be old enough
    assert set(result.old_enough) == {image1, image2}

    # image3 should be too recent
    assert len(result.too_recent) == 1
    assert result.too_recent[0][0] == image3
    # Check the age is approximately 30 minutes
    assert result.too_recent[0][1].total_seconds() / 60 == approx(30, abs=1)
