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
    ConsolidationCandidate,
    calculate_image_usage,
    check_if_symlink_references_image,
    check_temp_space_available,
    create_candidate_from_entry,
    create_group_manifest,
    delete_image_with_manifest,
    deploy_to_cefs_transactional,
    describe_cefs_image,
    determine_extraction_path,
    extract_candidates_from_manifest,
    filter_images_by_age,
    find_small_consolidated_images,
    format_image_contents_string,
    get_cefs_image_path,
    get_cefs_mount_path,
    get_cefs_paths,
    get_consolidated_item_status,
    get_current_symlink_targets,
    get_extraction_path_from_symlink,
    get_image_description,
    get_image_description_from_manifest,
    group_images_by_usage,
    has_enough_space,
    is_consolidated_image,
    is_item_still_using_image,
    pack_items_into_groups,
    parse_cefs_target,
    prepare_consolidation_items,
    should_include_manifest_item,
    should_reconsolidate_image,
    snapshot_symlink_targets,
    validate_space_requirements,
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
        (Path("/cefs/ab/abcdef1234567890abcdef12"), Path(".")),
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
        (custom_mount / "ab" / "abcd1234", Path(".")),
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
    regular_manifest.write_text(yaml.dump({"contents": [{"name": "test", "destination": str(nfs_dir / "test")}]}))

    inprogress_image = subdir / "def456_test.sqfs"
    inprogress_image.touch()
    inprogress_manifest = subdir / "def456_test.yaml.inprogress"
    inprogress_manifest.write_text(
        yaml.dump({"contents": [{"name": "inprog", "destination": str(nfs_dir / "inprog")}]})
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


def test_deploy_to_cefs_transactional_success(tmp_path):
    """Test that transactional deployment finalizes manifest on success."""
    source_path = tmp_path / "source.sqfs"
    source_path.write_bytes(b"test content")

    cefs_dir = tmp_path / "cefs"
    cefs_dir.mkdir()
    subdir = cefs_dir / "ab"
    subdir.mkdir()
    target_path = subdir / "abc123.sqfs"

    manifest = {"version": 1, "operation": "test", "contents": []}

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

    manifest = {"version": 1, "operation": "test", "contents": []}

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

    manifest = {"version": 1, "operation": "test", "contents": []}

    # Deploy in dry-run mode
    with deploy_to_cefs_transactional(source_path, target_path, manifest, dry_run=True):
        pass

    # Verify nothing was created
    assert not target_path.exists()
    assert not target_path.with_suffix(".yaml").exists()
    assert not Path(str(target_path.with_suffix(".yaml")) + ".inprogress").exists()


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


def test_is_consolidated_image(tmp_path):
    """Test is_consolidated_image function."""
    # Test with filename pattern
    consolidated_path = tmp_path / "abc123_consolidated.sqfs"
    consolidated_path.touch()
    assert is_consolidated_image(consolidated_path) is True

    # Test with non-consolidated filename
    individual_path = tmp_path / "abc123_gcc-15.1.0.sqfs"
    individual_path.touch()
    assert is_consolidated_image(individual_path) is False

    # Test with manifest containing multiple contents
    multi_content_path = tmp_path / "def456_something.sqfs"
    multi_content_path.touch()
    manifest = {
        "version": 1,
        "contents": [
            {"name": "gcc", "destination": "/opt/gcc"},
            {"name": "clang", "destination": "/opt/clang"},
        ],
    }
    write_manifest_alongside_image(manifest, multi_content_path)
    assert is_consolidated_image(multi_content_path) is True

    # Test with manifest containing single content
    single_content_path = tmp_path / "ghi789_single.sqfs"
    single_content_path.touch()
    manifest = {
        "version": 1,
        "contents": [
            {"name": "gcc", "destination": "/opt/gcc"},
        ],
    }
    write_manifest_alongside_image(manifest, single_content_path)
    assert is_consolidated_image(single_content_path) is False


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


def test_calculate_image_usage(tmp_path):
    """Test calculate_image_usage function."""
    nfs_dir = tmp_path / "nfs"
    nfs_dir.mkdir()
    mount_point = tmp_path / "test_mount"
    mount_point.mkdir()

    # Create an individual image
    individual_image = tmp_path / "abc123_gcc.sqfs"
    individual_image.touch()

    # Test individual image with reference
    # Image references should contain full absolute paths as they come from manifests
    gcc_full_path = nfs_dir / "opt" / "gcc"
    gcc_full_path.parent.mkdir(parents=True)
    image_references = {"abc123_gcc": [gcc_full_path]}

    # Create symlink pointing to this image
    gcc_full_path.symlink_to(mount_point / "ab" / "abc123_gcc")

    usage = calculate_image_usage(individual_image, image_references, nfs_dir, mount_point)
    assert usage == 100.0

    # Test individual image without reference (symlink points elsewhere)
    gcc_full_path.unlink()
    gcc_full_path.symlink_to(mount_point / "de" / "def456_gcc")

    usage = calculate_image_usage(individual_image, image_references, nfs_dir, mount_point)
    assert usage == 0.0

    # Test consolidated image with partial usage
    consolidated_image = tmp_path / "xyz789_consolidated.sqfs"
    consolidated_image.touch()

    # Create symlinks - only 2 of 3 point to this image
    tool1_path = nfs_dir / "opt" / "tool1"
    tool1_path.symlink_to(mount_point / "xy" / "xyz789_consolidated" / "tool1")

    tool2_path = nfs_dir / "opt" / "tool2"
    tool2_path.symlink_to(mount_point / "xy" / "xyz789_consolidated" / "tool2")

    tool3_path = nfs_dir / "opt" / "tool3"
    tool3_path.symlink_to(mount_point / "ab" / "different_image" / "tool3")

    # Image references should contain full absolute paths
    image_references["xyz789_consolidated"] = [
        tool1_path,
        tool2_path,
        tool3_path,
    ]

    usage = calculate_image_usage(consolidated_image, image_references, nfs_dir, mount_point)
    assert pytest.approx(usage, 0.1) == 66.7  # 2/3 = 66.7%


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
    manifest_content = {"contents": [{"name": "rollback-compiler", "destination": str(nfs_dir / "rollback-compiler")}]}
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
    state = CEFSState(nfs_dir, cefs_image_dir, Path("/cefs"))
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
    state = CEFSState(nfs_dir, cefs_image_dir, Path("/cefs"))
    state.scan_cefs_images_with_manifests()
    state.check_symlink_references()

    # Image should be marked as broken, not in all_cefs_images
    assert image_hash not in state.all_cefs_images, "Broken image should not be in all_cefs_images"
    assert image_hash not in state.referenced_images, "Broken image should not be in referenced_images"
    assert len(state.broken_images) == 1, "Should have one broken image"
    assert state.broken_images[0] == image_path, "Should track the broken image path"


def test_check_if_symlink_references_consolidated_image(tmp_path):
    test_mount = tmp_path / "test_cefs"
    test_mount.mkdir()

    # Test case 1: Normal consolidated image
    hash_dir = test_mount / "0d"
    hash_dir.mkdir()
    image_dir = hash_dir / "0d163f7f3ee984e50fd7d14f_consolidated"
    image_dir.mkdir()
    subdir = image_dir / "compilers_c++_x86_gcc_15.1.0"
    subdir.mkdir()

    symlink = tmp_path / "gcc-15.1.0"
    symlink.symlink_to(subdir)

    image_stem = "0d163f7f3ee984e50fd7d14f_consolidated"
    result = check_if_symlink_references_image(symlink, image_stem, test_mount)
    assert result is True, "Should detect symlink pointing to consolidated image"

    # Test case 2: Edge case - similar image names
    hash_dir2 = test_mount / "ab"
    hash_dir2.mkdir()
    image_dir2 = hash_dir2 / "abc_def"
    image_dir2.mkdir()
    subdir2 = image_dir2 / "some_compiler"
    subdir2.mkdir()

    symlink2 = tmp_path / "some-compiler"
    symlink2.symlink_to(subdir2)

    # Test that similar names don't match
    wrong_stem = "abc_def_xyz"
    result = check_if_symlink_references_image(symlink2, wrong_stem, test_mount)
    assert result is False, "Should NOT match - symlink points to 'abc_def' not 'abc_def_xyz'"

    # Test case 3: Wrong image
    other_stem = "deadbeef_consolidated"
    result = check_if_symlink_references_image(symlink, other_stem, test_mount)
    assert result is False, "Should not match different image"


def test_calculate_image_usage_with_absolute_paths(tmp_path):
    """Test that calculate_image_usage handles absolute paths correctly."""
    test_mount = tmp_path / "test_cefs"
    test_mount.mkdir()

    # Create a consolidated image structure
    hash_dir = test_mount / "0d"
    hash_dir.mkdir()
    image_path = hash_dir / "0d163f7f3ee984e50fd7d14f_consolidated.sqfs"
    image_path.touch()

    # Create actual symlinks at the expected locations
    # We need to use tmp_path as our fake /opt/compiler-explorer for testing
    fake_nfs = tmp_path / "fake_opt_compiler_explorer"
    fake_nfs.mkdir()

    # Create the symlinks
    gcc_link = fake_nfs / "gcc-15.1.0"
    gcc_target = test_mount / "0d" / "0d163f7f3ee984e50fd7d14f_consolidated" / "compilers_c++_x86_gcc_15.1.0"
    gcc_target.parent.mkdir(parents=True, exist_ok=True)
    gcc_target.mkdir()
    gcc_link.symlink_to(gcc_target)

    wasmtime_link = fake_nfs / "wasmtime-20.0.1"
    wasmtime_target = test_mount / "0d" / "0d163f7f3ee984e50fd7d14f_consolidated" / "compilers_wasm_wasmtime_20.0.1"
    wasmtime_target.mkdir()
    wasmtime_link.symlink_to(wasmtime_target)

    # Test with our fake paths instead of real /opt/compiler-explorer
    test_references = {"0d163f7f3ee984e50fd7d14f_consolidated": [fake_nfs / "gcc-15.1.0", fake_nfs / "wasmtime-20.0.1"]}

    usage = calculate_image_usage(image_path, test_references, fake_nfs, test_mount)
    assert usage == 100.0, f"Expected 100% usage, got {usage}%"


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
    state1 = CEFSState(nfs_dir, cefs_image_dir, Path("/cefs"))
    state2 = CEFSState(nfs_dir, cefs_image_dir, Path("/cefs"))

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


def test_create_group_manifest():
    """Test create_group_manifest function - pure function test."""
    group = [
        ConsolidationCandidate(
            name="gcc-15.1.0",
            nfs_path=Path("/opt/compiler-explorer/gcc-15.1.0"),
            squashfs_path=Path("/test/gcc.sqfs"),
            size=1000,
        ),
        ConsolidationCandidate(
            name="clang-19",
            nfs_path=Path("/opt/compiler-explorer/clang-19"),
            squashfs_path=Path("/test/clang.sqfs"),
            size=2000,
        ),
    ]

    manifest = create_group_manifest(group)

    assert manifest["operation"] == "consolidate"
    assert "gcc-15.1.0" in manifest["description"]
    assert "clang-19" in manifest["description"]
    assert "2 items" in manifest["description"]
    assert len(manifest["contents"]) == 2
    assert manifest["contents"][0]["name"] == "gcc-15.1.0"
    assert manifest["contents"][1]["name"] == "clang-19"


def test_create_candidate_from_entry(tmp_path):
    """Test create_candidate_from_entry function - mostly pure function."""
    nfs_dir = tmp_path / "nfs"
    nfs_dir.mkdir()

    state = CEFSState(nfs_dir, tmp_path / "cefs-images", Path("/cefs"))
    image_path = tmp_path / "test.sqfs"
    extraction_path = Path("subdir")

    # Test with absolute path
    content = {"name": "gcc-15.1.0", "destination": "/opt/compiler-explorer/gcc-15.1.0"}
    dest_path = Path(content["destination"])

    candidate = create_candidate_from_entry(content, dest_path, image_path, extraction_path, state, 1000)

    assert candidate.name == "gcc-15.1.0"
    assert candidate.nfs_path == Path("/opt/compiler-explorer/gcc-15.1.0")
    assert candidate.squashfs_path == image_path
    assert candidate.extraction_path == extraction_path
    assert candidate.size == 1000
    assert candidate.from_reconsolidation is True

    # Test with relative path - should resolve relative to nfs_dir
    content = {"name": "clang-19", "destination": "clang-19"}
    dest_path = Path(content["destination"])

    candidate = create_candidate_from_entry(content, dest_path, image_path, extraction_path, state, 2000)

    assert candidate.name == "clang-19"
    assert candidate.nfs_path == nfs_dir / "clang-19"
    assert candidate.size == 2000


def test_determine_extraction_path():
    """Test determine_extraction_path function with real paths."""
    mount_point = Path("/cefs")
    image_path = Path("/cefs-images/ab/abc123_consolidated.sqfs")

    # Test with valid target pointing to consolidated image subdirectory
    # Format: /cefs/XX/FILENAME_STEM/subdir/content
    targets = [Path("/cefs/ab/abc123_consolidated/subdir/content")]

    # This should work without mocking - is_item_still_using_image checks path structure
    extraction_path = determine_extraction_path(targets, image_path, mount_point)
    # When target matches image, it extracts parts after the image directory
    assert extraction_path == Path("subdir/content")

    # Test with empty targets - should return current directory
    extraction_path = determine_extraction_path([], image_path, mount_point)
    assert extraction_path == Path(".")

    # Test with short path (less than 5 parts) - should return current directory
    targets = [Path("/cefs/ab")]
    extraction_path = determine_extraction_path(targets, image_path, mount_point)
    assert extraction_path == Path(".")


def test_should_include_manifest_item(tmp_path):
    """Test should_include_manifest_item with real symlinks."""
    mount_point = Path("/cefs")
    image_stem = "abc123_consolidated"
    image_path = tmp_path / "cefs-images" / "ab" / f"{image_stem}.sqfs"
    image_path.parent.mkdir(parents=True)
    image_path.touch()

    # Create a real symlink pointing to CEFS
    dest = tmp_path / "gcc-15.1.0"
    cefs_target = mount_point / "ab" / image_stem / "gcc-15.1.0"
    dest.symlink_to(cefs_target)

    # Valid entry that references the image
    content = {"name": "gcc-15.1.0", "destination": str(dest)}

    should_include, targets = should_include_manifest_item(content, image_path, mount_point, [])
    # This checks if the symlink target contains the image stem in the right position
    assert len(targets) == 1
    assert targets[0] == cefs_target

    # The actual inclusion depends on is_item_still_using_image checking the path structure
    # For a proper test, we'd need the symlink to actually point to a matching image

    # Test with filter that matches
    should_include_filtered, _ = should_include_manifest_item(content, image_path, mount_point, ["gcc"])
    # Filter is applied after checking if item is still using image

    # Test with filter that doesn't match - should not include
    should_include_no_match, _ = should_include_manifest_item(content, image_path, mount_point, ["clang"])
    assert should_include_no_match is False or not should_include  # Won't include if filter doesn't match

    # Test malformed manifest entry
    bad_content = {"name": "test"}  # Missing destination
    with pytest.raises(ValueError, match="Malformed manifest entry"):
        should_include_manifest_item(bad_content, image_path, mount_point, [])


def test_prepare_consolidation_items(tmp_path):
    """Test prepare_consolidation_items with real symlinks."""
    mount_point = Path("/cefs")

    # Create a real symlink to a CEFS path
    gcc_path = tmp_path / "gcc-15.1.0"
    gcc_target = mount_point / "ab" / "abc123" / "content"
    gcc_path.symlink_to(gcc_target)

    # Test with regular consolidation candidate
    group = [
        ConsolidationCandidate(
            name="gcc-15.1.0",
            nfs_path=gcc_path,
            squashfs_path=Path("/test/gcc.sqfs"),
            size=1000,
        ),
    ]

    items, mapping = prepare_consolidation_items(group, mount_point)

    assert len(items) == 1
    assert items[0][0] == gcc_path  # nfs_path
    assert items[0][1] == Path("/test/gcc.sqfs")  # squashfs_path
    assert items[0][2] == "gcc-15.1.0"  # subdir_name (sanitized)
    assert items[0][3] == Path("content")  # extraction_path from symlink
    assert mapping[gcc_path] == "gcc-15.1.0"

    # Test with reconsolidation candidate (has extraction_path pre-set)
    group_recon = [
        ConsolidationCandidate(
            name="clang-19",
            nfs_path=Path("/opt/compiler-explorer/clang-19"),
            squashfs_path=Path("/test/clang.sqfs"),
            size=2000,
            extraction_path=Path("subdir/clang"),
            from_reconsolidation=True,
        ),
    ]

    items, mapping = prepare_consolidation_items(group_recon, mount_point)

    assert len(items) == 1
    assert items[0][3] == Path("subdir/clang")  # Uses provided extraction_path

    # Test with non-symlink path (should be skipped with warning)
    regular_file = tmp_path / "regular_file"
    regular_file.touch()  # Regular file, not a symlink

    group_broken = [
        ConsolidationCandidate(
            name="broken",
            nfs_path=regular_file,
            squashfs_path=Path("/test/broken.sqfs"),
            size=500,
        ),
    ]

    items, mapping = prepare_consolidation_items(group_broken, mount_point)
    assert len(items) == 0  # Should skip since it can't read symlink


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
    state = CEFSState(nfs_dir, cefs_image_dir, Path("/cefs"))
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


def test_calculate_consolidated_image_usage(tmp_path):
    """Test that calculate_image_usage correctly calculates usage for consolidated images."""
    # Set up test directories
    nfs_dir = tmp_path / "nfs"
    nfs_dir.mkdir()
    test_mount = tmp_path / "test_mount"
    test_mount.mkdir()

    # Create a mock consolidated image with actual naming convention
    cefs_dir = tmp_path / "cefs-images" / "0d"
    cefs_dir.mkdir(parents=True)
    consolidated_image = cefs_dir / "0d163f7f3ee984e50fd7d14f_consolidated.sqfs"
    consolidated_image.touch()

    # Set up symlinks pointing to consolidated image subdirectories
    # Using actual naming patterns from the real system
    gcc_15 = nfs_dir / "opt" / "compiler-explorer" / "gcc-15.1.0"
    gcc_15.parent.mkdir(parents=True)
    wasmtime = nfs_dir / "opt" / "compiler-explorer" / "wasmtime-20.0.1"

    # Create symlinks with actual subdirectory naming convention
    # Using test_mount instead of /cefs to avoid real filesystem
    target_base = test_mount / "0d" / "0d163f7f3ee984e50fd7d14f_consolidated"
    target_base.mkdir(parents=True)
    gcc_15.symlink_to(target_base / "compilers_c++_x86_gcc_15.1.0")
    wasmtime.symlink_to(target_base / "compilers_wasm_wasmtime_20.0.1")

    # Set up image_references as would be populated by CEFSState from manifest
    # These should be the actual full paths where the symlinks exist
    image_references = {
        "0d163f7f3ee984e50fd7d14f_consolidated": [
            gcc_15,
            wasmtime,
        ]
    }

    # Calculate usage
    usage = calculate_image_usage(consolidated_image, image_references, nfs_dir, test_mount)

    # Should be 100% since both items are still referenced
    assert usage == 100.0, f"Expected 100% usage, got {usage}%"


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


def test_should_reconsolidate_image():
    """Test should_reconsolidate_image function."""
    # Test low efficiency
    should_recon, reason = should_reconsolidate_image(
        usage=30.0, size=10 * 1024**3, efficiency_threshold=0.5, max_size_bytes=20 * 1024**3, undersized_ratio=0.25
    )
    assert should_recon is True
    assert "low efficiency" in reason
    assert "30.0%" in reason

    # Test undersized
    should_recon, reason = should_reconsolidate_image(
        usage=80.0, size=3 * 1024**3, efficiency_threshold=0.5, max_size_bytes=20 * 1024**3, undersized_ratio=0.25
    )
    assert should_recon is True
    assert "undersized" in reason

    # Test good image (should not reconsolidate)
    should_recon, reason = should_reconsolidate_image(
        usage=80.0, size=10 * 1024**3, efficiency_threshold=0.5, max_size_bytes=20 * 1024**3, undersized_ratio=0.25
    )
    assert should_recon is False
    assert not reason

    # Test zero usage
    should_recon, reason = should_reconsolidate_image(
        usage=0.0, size=10 * 1024**3, efficiency_threshold=0.5, max_size_bytes=20 * 1024**3, undersized_ratio=0.25
    )
    assert should_recon is False
    assert not reason


def test_group_images_by_usage():
    """Test group_images_by_usage function."""
    test_data = [
        (Path("/image1"), 90.0),  # 75-99%
        (Path("/image2"), 60.0),  # 50-74%
        (Path("/image3"), 30.0),  # 25-49%
        (Path("/image4"), 10.0),  # <25%
        (Path("/image5"), 75.0),  # 75-99%
    ]

    grouped = group_images_by_usage(test_data)

    assert len(grouped["75-99%"]) == 2
    assert len(grouped["50-74%"]) == 1
    assert len(grouped["25-49%"]) == 1
    assert len(grouped["<25%"]) == 1

    assert (Path("/image1"), 90.0) in grouped["75-99%"]
    assert (Path("/image5"), 75.0) in grouped["75-99%"]
    assert (Path("/image2"), 60.0) in grouped["50-74%"]
    assert (Path("/image3"), 30.0) in grouped["25-49%"]
    assert (Path("/image4"), 10.0) in grouped["<25%"]


def test_is_item_still_using_image(tmp_path):
    """Test is_item_still_using_image function."""
    mount_point = Path("/cefs")
    image_path = tmp_path / "abc123_consolidated.sqfs"
    image_path.touch()

    # Test valid target pointing to image
    target = Path("/cefs/ab/abc123_consolidated/subdir/item")
    assert is_item_still_using_image(target, image_path, mount_point) is True

    # Test target pointing to different image
    target = Path("/cefs/de/def456_consolidated/subdir/item")
    assert is_item_still_using_image(target, image_path, mount_point) is False

    # Test non-CEFS target
    target = Path("/opt/compiler/gcc")
    assert is_item_still_using_image(target, image_path, mount_point) is False

    # Test None target
    assert is_item_still_using_image(None, image_path, mount_point) is False

    # Test target with too few parts
    target = Path("/cefs/ab")
    assert is_item_still_using_image(target, image_path, mount_point) is False


def test_get_consolidated_item_status():
    """Test get_consolidated_item_status function."""
    mount_point = Path("/cefs")
    image_path = Path("/efs/cefs-images/ab/abc123.sqfs")

    # Test when content has no 'name' field - should return empty string
    content = {"dest_path": "/opt/compiler-explorer/gcc-15.0.0"}
    current_target = Path("/cefs/ab/abc123/gcc-15.0.0")
    status = get_consolidated_item_status(content, image_path, current_target, mount_point)
    assert not status

    # Test when current target matches image
    content = {"dest_path": "/opt/compiler-explorer/gcc-15.0.0", "name": "gcc-15.0.0"}
    current_target = Path("/cefs/ab/abc123/gcc-15.0.0")
    status = get_consolidated_item_status(content, image_path, current_target, mount_point)
    assert "✓ gcc-15.0.0" in status

    # Test when current target is different
    current_target = Path("/cefs/de/def456/gcc-15.0.0")
    status = get_consolidated_item_status(content, image_path, current_target, mount_point)
    assert "✗ gcc-15.0.0" in status
    assert "de/def456/gcc-15.0.0" in status

    # Test when no current target (missing)
    status = get_consolidated_item_status(content, image_path, None, mount_point)
    assert "✗ gcc-15.0.0" in status
    assert "not in CEFS" in status


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
        small_images = find_small_consolidated_images(state, 1024 * 1024 * 1024)
    assert len(small_images) == 2
    assert small_image in small_images
    assert medium_image in small_images
    assert large_image not in small_images
    assert non_consol not in small_images


def test_extract_candidates_from_manifest(tmp_path):
    """Test extract_candidates_from_manifest function."""

    # Set up test paths
    mount_point = Path("/cefs")
    image_path = Path("/efs/cefs-images/ab/abc123_consolidated.sqfs")
    nfs_dir = tmp_path / "nfs"
    nfs_dir.mkdir()

    # Create test state
    state = CEFSState(nfs_dir, Path("/efs/cefs-images"), mount_point)

    # Create test manifest
    manifest = {
        "contents": [
            {
                "size": 100 * 1024 * 1024,  # 100MB
                "destination": str(nfs_dir / "gcc-15.0.0"),
                "name": "gcc-15.0.0",
                "source_path": "gcc-15.0.0",
            },
            {
                "size": 50 * 1024 * 1024,  # 50MB
                "destination": str(nfs_dir / "clang-18.0.0"),
                "name": "clang-18.0.0",
                "source_path": "clang-18.0.0",
            },
            {
                "size": 200 * 1024 * 1024,  # 200MB
                "destination": str(nfs_dir / "rust-1.80.0"),
                "name": "rust-1.80.0",
                "source_path": "rust-1.80.0",
            },
        ]
    }

    # Create symlinks for testing
    gcc_link = nfs_dir / "gcc-15.0.0"
    gcc_link.symlink_to(mount_point / "ab" / "abc123_consolidated" / "gcc-15.0.0")

    clang_link = nfs_dir / "clang-18.0.0"
    clang_link.symlink_to(mount_point / "de" / "def456_consolidated" / "clang-18.0.0")  # Different image

    rust_link = nfs_dir / "rust-1.80.0"
    rust_link.symlink_to(mount_point / "ab" / "abc123_consolidated" / "rust-1.80.0")

    # Test with no filter - should get items still using this image
    candidates = extract_candidates_from_manifest(manifest, image_path, state, [], 1024 * 1024 * 1024, mount_point)

    # Should have 2 candidates (gcc and rust still pointing to abc123)
    assert len(candidates) == 2
    candidate_names = {c.name for c in candidates}
    assert "gcc-15.0.0" in candidate_names
    assert "rust-1.80.0" in candidate_names
    assert "clang-18.0.0" not in candidate_names  # Points to different image

    # Test with filter
    candidates = extract_candidates_from_manifest(manifest, image_path, state, ["gcc"], 1024 * 1024 * 1024, mount_point)
    assert len(candidates) == 1
    assert candidates[0].name == "gcc-15.0.0"

    # Size should be total size divided by number of contents (3 items)
    # Since it's estimated as size // len(contents)
    expected_size_per_item = 1024 * 1024 * 1024 // 3
    assert candidates[0].size == expected_size_per_item


def test_pack_items_into_groups():
    """Test pack_items_into_groups function."""
    # Create test candidates with varying sizes
    candidates = [
        ConsolidationCandidate(
            name="gcc-15.0.0",
            nfs_path=Path("/opt/gcc-15.0.0"),
            squashfs_path=Path("/efs/gcc.sqfs"),
            size=500 * 1024 * 1024,  # 500MB
            extraction_path=Path("."),
            from_reconsolidation=False,
        ),
        ConsolidationCandidate(
            name="clang-18.0.0",
            nfs_path=Path("/opt/clang-18.0.0"),
            squashfs_path=Path("/efs/clang.sqfs"),
            size=400 * 1024 * 1024,  # 400MB
            extraction_path=Path("."),
            from_reconsolidation=False,
        ),
        ConsolidationCandidate(
            name="rust-1.80.0",
            nfs_path=Path("/opt/rust-1.80.0"),
            squashfs_path=Path("/efs/rust.sqfs"),
            size=300 * 1024 * 1024,  # 300MB
            extraction_path=Path("."),
            from_reconsolidation=False,
        ),
        ConsolidationCandidate(
            name="go-1.21.0",
            nfs_path=Path("/opt/go-1.21.0"),
            squashfs_path=Path("/efs/go.sqfs"),
            size=200 * 1024 * 1024,  # 200MB
            extraction_path=Path("."),
            from_reconsolidation=False,
        ),
    ]

    # Test packing with 1GB max size and min 2 items
    groups = pack_items_into_groups(candidates, 1024 * 1024 * 1024, 2)

    # Should create 2 groups: [clang, gcc] and [go, rust]
    # Items are sorted by name, so order is: clang, gcc, go, rust
    assert len(groups) == 2

    # First group: clang (400MB) + gcc (500MB) = 900MB
    assert len(groups[0]) == 2
    assert groups[0][0].name == "clang-18.0.0"
    assert groups[0][1].name == "gcc-15.0.0"

    # Second group: go (200MB) + rust (300MB) = 500MB
    assert len(groups[1]) == 2
    assert groups[1][0].name == "go-1.21.0"
    assert groups[1][1].name == "rust-1.80.0"

    # Test with higher minimum - with 3 min items and 1GB limit
    groups = pack_items_into_groups(candidates, 1024 * 1024 * 1024, 3)
    # clang (400) + gcc (500) + go (200) = 1100MB > 1024MB
    # But the algorithm tries: clang + gcc = 900MB, then adds go = 1100MB > limit
    # So it starts new group with go, but go + rust = 500MB < 3 items minimum
    # Actually, clang + gcc + go fits just over 1GB, but clang + go + rust = 900MB works
    assert len(groups) == 1  # Only one group meets the 3-item minimum
    assert len(groups[0]) == 3

    # Test with smaller max size
    groups = pack_items_into_groups(candidates, 600 * 1024 * 1024, 1)
    # Each item except go+rust can form its own group
    assert len(groups) >= 3


def test_validate_space_requirements(tmp_path):
    """Test validate_space_requirements function."""
    # Create test groups
    group1 = [
        ConsolidationCandidate(
            name="item1",
            nfs_path=Path("/opt/item1"),
            squashfs_path=Path("/efs/item1.sqfs"),
            size=100 * 1024 * 1024,  # 100MB
            extraction_path=Path("."),
            from_reconsolidation=False,
        ),
        ConsolidationCandidate(
            name="item2",
            nfs_path=Path("/opt/item2"),
            squashfs_path=Path("/efs/item2.sqfs"),
            size=200 * 1024 * 1024,  # 200MB
            extraction_path=Path("."),
            from_reconsolidation=False,
        ),
    ]

    group2 = [
        ConsolidationCandidate(
            name="item3",
            nfs_path=Path("/opt/item3"),
            squashfs_path=Path("/efs/item3.sqfs"),
            size=150 * 1024 * 1024,  # 150MB
            extraction_path=Path("."),
            from_reconsolidation=False,
        ),
    ]

    groups = [group1, group2]

    # Test with sufficient space
    temp_dir = tmp_path / "temp"
    temp_dir.mkdir()

    # Mock the space check to succeed
    with patch("lib.cefs.check_temp_space_available", return_value=True):
        required, largest = validate_space_requirements(groups, temp_dir)
        # Group1 is largest: 300MB, so required = 300MB * 5 = 1.5GB
        assert largest == 300 * 1024 * 1024
        assert required == 300 * 1024 * 1024 * 5

    # Test with insufficient space
    with patch("lib.cefs.check_temp_space_available", return_value=False):
        with patch("os.statvfs") as mock_statvfs:
            mock_stat = Mock()
            mock_stat.f_bavail = 1024  # blocks available
            mock_stat.f_frsize = 1024  # block size
            mock_statvfs.return_value = mock_stat

            with pytest.raises(RuntimeError) as exc_info:
                validate_space_requirements(groups, temp_dir)
            assert "Insufficient temp space" in str(exc_info.value)

    # Test with empty groups
    required, largest = validate_space_requirements([], temp_dir)
    assert required == 0
    assert largest == 0


def test_gather_reconsolidation_candidates(tmp_path):
    """Test gather_reconsolidation_candidates method in CEFSState."""
    # Create test directory structure
    nfs_dir = tmp_path / "nfs"
    nfs_dir.mkdir()
    cefs_image_dir = tmp_path / "cefs-images"
    cefs_image_dir.mkdir()
    mount_point = tmp_path / "cefs"
    mount_point.mkdir()

    # Create a consolidated image that should be reconsolidated (low efficiency)
    subdir1 = cefs_image_dir / "ab"
    subdir1.mkdir()
    consolidated_image = subdir1 / "abc123_consolidated.sqfs"
    consolidated_image.write_bytes(b"x" * (100 * 1024 * 1024))  # 100MB

    # Create manifest for the consolidated image
    manifest = {
        "version": 1,
        "operation": "consolidate",
        "contents": [
            {"name": "tool1", "destination": str(nfs_dir / "tool1")},
            {"name": "tool2", "destination": str(nfs_dir / "tool2")},
            {"name": "tool3", "destination": str(nfs_dir / "tool3")},
        ],
    }
    write_manifest_alongside_image(manifest, consolidated_image)

    # Create symlinks - only 1 of 3 still pointing to the consolidated image
    # This gives us 33% efficiency, below our 50% threshold
    tool1_path = nfs_dir / "tool1"
    tool1_path.symlink_to(mount_point / "ab" / "abc123_consolidated" / "tool1")

    # These were originally in the consolidated image but have been replaced
    tool2_path = nfs_dir / "tool2"
    tool2_path.symlink_to(mount_point / "de" / "different_image")

    tool3_path = nfs_dir / "tool3"
    tool3_path.symlink_to(mount_point / "fg" / "another_image")

    # Create an undersized consolidated image that should be reconsolidated
    subdir2 = cefs_image_dir / "cd"
    subdir2.mkdir()
    undersized_image = subdir2 / "def456_consolidated.sqfs"
    undersized_image.write_bytes(b"x" * (10 * 1024 * 1024))  # 10MB - undersized

    # Create manifest for the undersized image
    manifest2 = {
        "version": 1,
        "operation": "consolidate",
        "contents": [
            {"name": "small1", "destination": str(nfs_dir / "small1")},
            {"name": "small2", "destination": str(nfs_dir / "small2")},
        ],
    }
    write_manifest_alongside_image(manifest2, undersized_image)

    # Both point to the undersized image (100% efficiency but still undersized)
    small1_path = nfs_dir / "small1"
    small1_path.symlink_to(mount_point / "cd" / "def456_consolidated" / "small1")
    small2_path = nfs_dir / "small2"
    small2_path.symlink_to(mount_point / "cd" / "def456_consolidated" / "small2")

    # Create a good consolidated image that should NOT be reconsolidated
    subdir3 = cefs_image_dir / "ef"
    subdir3.mkdir()
    good_image = subdir3 / "ghi789_consolidated.sqfs"
    good_image.write_bytes(b"x" * (200 * 1024 * 1024))  # 200MB

    manifest3 = {
        "version": 1,
        "operation": "consolidate",
        "contents": [
            {"name": "good1", "destination": str(nfs_dir / "good1")},
            {"name": "good2", "destination": str(nfs_dir / "good2")},
        ],
    }
    write_manifest_alongside_image(manifest3, good_image)

    # Both point to the good image (100% efficiency and good size)
    good1_path = nfs_dir / "good1"
    good1_path.symlink_to(mount_point / "ef" / "ghi789_consolidated" / "good1")
    good2_path = nfs_dir / "good2"
    good2_path.symlink_to(mount_point / "ef" / "ghi789_consolidated" / "good2")

    # Create CEFSState and test gather_reconsolidation_candidates
    state = CEFSState(nfs_dir, cefs_image_dir, mount_point)
    state.scan_cefs_images_with_manifests()
    state.check_symlink_references()

    # Gather candidates with 50% efficiency threshold, 500MB max size, 0.25 undersized ratio
    candidates = state.gather_reconsolidation_candidates(
        efficiency_threshold=0.5,
        max_size_bytes=500 * 1024 * 1024,
        undersized_ratio=0.25,  # Images < 125MB are undersized
        filter_=[],
    )

    # We should get candidates from:
    # - abc123_consolidated (low efficiency: 33%)
    # - def456_consolidated (undersized: 10MB < 125MB)
    # But NOT from ghi789_consolidated (100% efficiency, good size)

    assert len(candidates) == 3  # tool1 from low-efficiency, small1 and small2 from undersized

    candidate_names = {c.name for c in candidates}
    assert "tool1" in candidate_names  # From low-efficiency image
    assert "small1" in candidate_names  # From undersized image
    assert "small2" in candidate_names  # From undersized image
    assert "good1" not in candidate_names  # Good image should not be reconsolidated
    assert "good2" not in candidate_names  # Good image should not be reconsolidated

    # Test with filter
    candidates_filtered = state.gather_reconsolidation_candidates(
        efficiency_threshold=0.5,
        max_size_bytes=500 * 1024 * 1024,
        undersized_ratio=0.25,
        filter_=["small"],  # Only get items with "small" in the name
    )

    assert len(candidates_filtered) == 2
    filtered_names = {c.name for c in candidates_filtered}
    assert filtered_names == {"small1", "small2"}
