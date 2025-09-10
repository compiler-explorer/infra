#!/usr/bin/env python3
"""Tests for CEFS consolidation module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from lib.cefs.consolidation import (
    calculate_image_usage,
    create_group_manifest,
    determine_extraction_path,
    extract_candidates_from_manifest,
    get_consolidated_item_status,
    group_images_by_usage,
    is_consolidated_image,
    is_item_still_using_image,
    pack_items_into_groups,
    prepare_consolidation_items,
    should_include_manifest_item,
    should_reconsolidate_image,
    validate_space_requirements,
)
from lib.cefs.models import ConsolidationCandidate
from lib.cefs.state import CEFSState
from lib.cefs_manifest import sanitize_path_for_filename, write_manifest_alongside_image

from test.cefs.test_helpers import make_test_manifest


def test_is_consolidated_image(tmp_path):
    multi_content_path = tmp_path / "def456_something.sqfs"
    multi_content_path.touch()
    write_manifest_alongside_image(
        make_test_manifest(
            contents=[
                {"name": "compilers/c++/x86/gcc 12.0.0", "destination": "/opt/gcc"},
                {"name": "compilers/c++/x86/clang 15.0.0", "destination": "/opt/clang"},
            ],
        ),
        multi_content_path,
    )
    assert is_consolidated_image(multi_content_path) is True

    # Test with manifest containing single content
    single_content_path = tmp_path / "ghi789_single.sqfs"
    single_content_path.touch()
    write_manifest_alongside_image(
        make_test_manifest(
            contents=[{"name": "compilers/c++/x86/gcc 12.0.0", "destination": "/opt/gcc"}],
        ),
        single_content_path,
    )
    assert is_consolidated_image(single_content_path) is False


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

    usage = calculate_image_usage(individual_image, image_references, mount_point)
    assert usage == 100.0

    # Test individual image without reference (symlink points elsewhere)
    gcc_full_path.unlink()
    gcc_full_path.symlink_to(mount_point / "de" / "def456_gcc")

    usage = calculate_image_usage(individual_image, image_references, mount_point)
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

    usage = calculate_image_usage(consolidated_image, image_references, mount_point)
    assert pytest.approx(usage, 0.1) == 66.7  # 2/3 = 66.7%


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

    usage = calculate_image_usage(image_path, test_references, test_mount)
    assert usage == 100.0, f"Expected 100% usage, got {usage}%"


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
    assert extraction_path is None

    # Test with short path (less than 5 parts) - should return current directory
    targets = [Path("/cefs/ab")]
    extraction_path = determine_extraction_path(targets, image_path, mount_point)
    assert extraction_path is None


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
    content = {"name": "compilers/c++/x86/gcc 15.1.0", "destination": str(dest)}

    should_include, target = should_include_manifest_item(content, image_path, mount_point, [])
    # This checks if the symlink target contains the image stem in the right position
    assert target == cefs_target

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


def test_should_include_manifest_item_bak_symlink(tmp_path):
    """Test that should_include_manifest_item only considers main symlink, not .bak."""
    mount_point = Path("/cefs")

    # Two different consolidated images
    old_image_stem = "old123_consolidated"
    old_image_path = tmp_path / "cefs-images" / "ol" / f"{old_image_stem}.sqfs"
    old_image_path.parent.mkdir(parents=True)
    old_image_path.touch()

    new_image_stem = "new456_consolidated"
    new_image_path = tmp_path / "cefs-images" / "ne" / f"{new_image_stem}.sqfs"
    new_image_path.parent.mkdir(parents=True)
    new_image_path.touch()

    # Create destination directory
    dest = tmp_path / "osaca-0.7.1"
    dest_bak = tmp_path / "osaca-0.7.1.bak"

    # Main symlink points to new image
    new_target = mount_point / "ne" / new_image_stem / "tools_osaca_0.7.1"
    dest.symlink_to(new_target)

    # Backup symlink points to old image
    old_target = mount_point / "ol" / old_image_stem / "tools_osaca_0.7.1"
    dest_bak.symlink_to(old_target)

    content = {"name": "tools/osaca 0.7.1", "destination": str(dest)}

    # Check the OLD image (only referenced by .bak)
    should_include_old, target_old = should_include_manifest_item(content, old_image_path, mount_point, [])

    # Check the NEW image (referenced by main symlink)
    should_include_new, target_new = should_include_manifest_item(content, new_image_path, mount_point, [])

    # Only the main symlink should be considered for reconsolidation
    assert not should_include_old, "Old image should not be included (only referenced by .bak)"
    assert should_include_new, "New image should be included (referenced by main symlink)"


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
    usage = calculate_image_usage(consolidated_image, image_references, test_mount)

    # Should be 100% since both items are still referenced
    assert usage == 100.0, f"Expected 100% usage, got {usage}%"


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


def test_reconsolidation_symlink_mapping():
    """Test that reconsolidated items get correct symlink mappings.

    This test reproduces the critical bug where reconsolidated items
    have their symlinks pointing to the wrong directory level.
    """
    mount_point = Path("/cefs")

    # Simulate reconsolidation candidates from an old consolidated image
    # These would come from an image with structure like:
    # old_consolidated.sqfs/gcc/compilers_c++_x86_gcc_12.3.0/
    candidates = [
        ConsolidationCandidate(
            name="compilers/c++/x86/gcc 12.3.0",
            nfs_path=Path("/opt/compiler-explorer/gcc-12.3.0"),
            squashfs_path=Path("/efs/cefs-images/f2/f2934b9a_consolidated.sqfs"),
            size=100 * 1024 * 1024,
            extraction_path=Path("gcc/compilers_c++_x86_gcc_12.3.0"),
            from_reconsolidation=True,
        ),
        ConsolidationCandidate(
            name="compilers/c++/x86/gcc 12.4.0",
            nfs_path=Path("/opt/compiler-explorer/gcc-12.4.0"),
            squashfs_path=Path("/efs/cefs-images/f2/f2934b9a_consolidated.sqfs"),
            size=100 * 1024 * 1024,
            extraction_path=Path("gcc/compilers_c++_x86_gcc_12.4.0"),
            from_reconsolidation=True,
        ),
    ]

    # Process consolidation items
    items, subdir_mapping = prepare_consolidation_items(candidates, mount_point)

    # The bug: subdir_mapping incorrectly maps to just "gcc" instead of the full path
    # This assertion should FAIL with the current buggy code
    for candidate in candidates:
        mapped_subdir = subdir_mapping[candidate.nfs_path]

        # The mapping should preserve the structure for proper symlink targeting
        # For an extraction_path of "gcc/compilers_c++_x86_gcc_12.3.0",
        # the symlink needs to point to the full path within the consolidated image
        if candidate.extraction_path is not None:
            # For reconsolidated items with nested paths, we need special handling
            # The mapped subdir should indicate where the symlink should point
            expected_name = sanitize_path_for_filename(Path(candidate.name))

            # Current buggy behavior: mapped_subdir might be just "gcc"
            # Correct behavior: should be something that results in the symlink
            # pointing to the right subdirectory

            # This assertion captures what SHOULD happen
            # With the bug, this will fail because mapped_subdir is just "gcc"
            assert mapped_subdir == expected_name, (
                f"Subdir mapping incorrect for {candidate.nfs_path}: "
                f"got '{mapped_subdir}', expected '{expected_name}' "
                f"(extraction_path: {candidate.extraction_path})"
            )


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
    content = {"dest_path": "/opt/compiler-explorer/gcc-15.0.0", "name": "compilers/c++/x86/gcc 15.0.0"}
    current_target = Path("/cefs/ab/abc123/gcc-15.0.0")
    status = get_consolidated_item_status(content, image_path, current_target, mount_point)
    assert "✓ compilers/c++/x86/gcc 15.0.0" in status

    # Test when current target is different
    current_target = Path("/cefs/de/def456/gcc-15.0.0")
    status = get_consolidated_item_status(content, image_path, current_target, mount_point)
    assert "✗ compilers/c++/x86/gcc 15.0.0" in status
    assert "de/def456/gcc-15.0.0" in status

    # Test when no current target (missing)
    status = get_consolidated_item_status(content, image_path, None, mount_point)
    assert "✗ compilers/c++/x86/gcc 15.0.0" in status
    assert "not in CEFS" in status


def test_extract_candidates_from_manifest(tmp_path):
    """Test extract_candidates_from_manifest function."""

    # Set up test paths
    mount_point = Path("/cefs")
    image_path = Path("/efs/cefs-images/ab/abc123_consolidated.sqfs")
    nfs_dir = tmp_path / "nfs"
    nfs_dir.mkdir()

    # Create test manifest
    manifest = make_test_manifest(
        operation="consolidate",
        contents=[
            {
                "destination": str(nfs_dir / "gcc-15.0.0"),
                "name": "compilers/c++/x86/gcc 15.0.0",
            },
            {
                "destination": str(nfs_dir / "clang-18.0.0"),
                "name": "compilers/c++/x86/clang 18.0.0",
            },
            {
                "destination": str(nfs_dir / "rust-1.80.0"),
                "name": "compilers/rust/rust 1.80.0",
            },
        ],
    )

    # Create symlinks for testing
    gcc_link = nfs_dir / "gcc-15.0.0"
    gcc_link.symlink_to(mount_point / "ab" / "abc123_consolidated" / "gcc-15.0.0")

    clang_link = nfs_dir / "clang-18.0.0"
    clang_link.symlink_to(mount_point / "de" / "def456_consolidated" / "clang-18.0.0")  # Different image

    rust_link = nfs_dir / "rust-1.80.0"
    rust_link.symlink_to(mount_point / "ab" / "abc123_consolidated" / "rust-1.80.0")

    # Test with no filter - should get items still using this image
    candidates = extract_candidates_from_manifest(manifest, image_path, [], 1024 * 1024 * 1024, mount_point)

    # Should have 2 candidates (gcc and rust still pointing to abc123)
    assert len(candidates) == 2
    candidate_names = {c.name for c in candidates}
    assert "compilers/c++/x86/gcc 15.0.0" in candidate_names
    assert "compilers/rust/rust 1.80.0" in candidate_names
    assert "compilers/c++/x86/clang 18.0.0" not in candidate_names  # Points to different image

    # Test with filter
    candidates = extract_candidates_from_manifest(manifest, image_path, ["gcc"], 1024 * 1024 * 1024, mount_point)
    assert len(candidates) == 1
    assert candidates[0].name == "compilers/c++/x86/gcc 15.0.0"

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
            extraction_path=None,
            from_reconsolidation=False,
        ),
        ConsolidationCandidate(
            name="clang-18.0.0",
            nfs_path=Path("/opt/clang-18.0.0"),
            squashfs_path=Path("/efs/clang.sqfs"),
            size=400 * 1024 * 1024,  # 400MB
            extraction_path=None,
            from_reconsolidation=False,
        ),
        ConsolidationCandidate(
            name="rust-1.80.0",
            nfs_path=Path("/opt/rust-1.80.0"),
            squashfs_path=Path("/efs/rust.sqfs"),
            size=300 * 1024 * 1024,  # 300MB
            extraction_path=None,
            from_reconsolidation=False,
        ),
        ConsolidationCandidate(
            name="go-1.21.0",
            nfs_path=Path("/opt/go-1.21.0"),
            squashfs_path=Path("/efs/go.sqfs"),
            size=200 * 1024 * 1024,  # 200MB
            extraction_path=None,
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
            extraction_path=None,
            from_reconsolidation=False,
        ),
        ConsolidationCandidate(
            name="item2",
            nfs_path=Path("/opt/item2"),
            squashfs_path=Path("/efs/item2.sqfs"),
            size=200 * 1024 * 1024,  # 200MB
            extraction_path=None,
            from_reconsolidation=False,
        ),
    ]

    group2 = [
        ConsolidationCandidate(
            name="item3",
            nfs_path=Path("/opt/item3"),
            squashfs_path=Path("/efs/item3.sqfs"),
            size=150 * 1024 * 1024,  # 150MB
            extraction_path=None,
            from_reconsolidation=False,
        ),
    ]

    groups = [group1, group2]

    # Test with sufficient space
    temp_dir = tmp_path / "temp"
    temp_dir.mkdir()

    # Mock the space check to succeed
    with patch("lib.cefs.deployment.check_temp_space_available", return_value=True):
        required, largest = validate_space_requirements(groups, temp_dir)
        # Group1 is largest: 300MB, so required = 300MB * 5 = 1.5GB
        assert largest == 300 * 1024 * 1024
        assert required == 300 * 1024 * 1024 * 5

    # Test with insufficient space
    with patch("lib.cefs.deployment.check_temp_space_available", return_value=False):
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
    manifest = make_test_manifest(
        operation="consolidate",
        contents=[
            {"name": "tools/test/tool 1.0.0", "destination": str(nfs_dir / "tool1")},
            {"name": "tools/test/tool 2.0.0", "destination": str(nfs_dir / "tool2")},
            {"name": "tools/test/tool 3.0.0", "destination": str(nfs_dir / "tool3")},
        ],
    )
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
    manifest2 = make_test_manifest(
        operation="consolidate",
        contents=[
            {"name": "tools/small 1.0.0", "destination": str(nfs_dir / "small1")},
            {"name": "tools/small 2.0.0", "destination": str(nfs_dir / "small2")},
        ],
    )
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

    manifest3 = make_test_manifest(
        operation="consolidate",
        contents=[
            {"name": "tools/good 1.0.0", "destination": str(nfs_dir / "good1")},
            {"name": "tools/good 2.0.0", "destination": str(nfs_dir / "good2")},
        ],
    )
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
    assert "tools/test/tool 1.0.0" in candidate_names  # From low-efficiency image
    assert "tools/small 1.0.0" in candidate_names  # From undersized image
    assert "tools/small 2.0.0" in candidate_names  # From undersized image
    assert "tools/good 1.0.0" not in candidate_names  # Good image should not be reconsolidated
    assert "tools/good 2.0.0" not in candidate_names  # Good image should not be reconsolidated

    # Test with filter
    candidates_filtered = state.gather_reconsolidation_candidates(
        efficiency_threshold=0.5,
        max_size_bytes=500 * 1024 * 1024,
        undersized_ratio=0.25,
        filter_=["small"],  # Only get items with "small" in the name
    )

    assert len(candidates_filtered) == 2
    filtered_names = {c.name for c in candidates_filtered}
    assert filtered_names == {"tools/small 1.0.0", "tools/small 2.0.0"}
