#!/usr/bin/env python3
"""Tests for CEFS gc module."""

from __future__ import annotations

import datetime
import os
import time
from pathlib import Path

import yaml
from lib.cefs.gc import (
    check_if_symlink_references_image,
    delete_image_with_manifest,
    filter_images_by_age,
)
from lib.cefs.state import CEFSState
from pytest import approx

from test.cefs.test_helpers import make_test_manifest


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
        manifest_content = make_test_manifest(
            contents=[{"name": f"tools/test/{hash_val} 1.0.0", "destination": str(nfs_dir / f"test-{hash_val}")}]
        )
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
    manifest_content = make_test_manifest(
        contents=[{"name": "compilers/test/compiler 1.0.0", "destination": str(nfs_dir / "test-compiler")}]
    )
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
    ref_manifest.write_text(
        yaml.dump(
            make_test_manifest(
                contents=[{"name": "compilers/c++/x86/gcc 11.0.0", "destination": str(nfs_dir / "gcc-11")}]
            )
        )
    )

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
        yaml.dump(
            make_test_manifest(
                contents=[{"name": "compilers/test/old 1.0.0", "destination": str(nfs_dir / "old-compiler")}]
            )
        )
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
        yaml.dump(
            make_test_manifest(
                contents=[{"name": "compilers/c++/x86/gcc 10.0.0", "destination": str(nfs_dir / "backup-gcc")}]
            )
        )
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
