#!/usr/bin/env python3
"""Tests for CEFS formatting module."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml
from lib.cefs.formatting import (
    classify_installable_location,
    format_image_contents_string,
    get_image_description,
    get_image_description_from_manifest,
    get_installable_current_locations,
)

from test.cefs.test_helpers import make_test_manifest


def test_get_image_description_from_manifest(tmp_path):
    image_path = tmp_path / "test.sqfs"
    manifest_path = image_path.with_suffix(".yaml")

    # Test with valid manifest
    manifest_path.write_text(
        yaml.dump(
            make_test_manifest(
                contents=[
                    {"name": "compilers/c++/x86/gcc 11.0.0", "destination": "/opt/gcc-11"},
                    {"name": "libraries/c++/boost 1.75.0", "destination": "/opt/boost"},
                ]
            )
        )
    )

    assert get_image_description_from_manifest(image_path) == [
        "compilers/c++/x86/gcc 11.0.0",
        "libraries/c++/boost 1.75.0",
    ]

    # Test with empty contents
    manifest_path.write_text(yaml.dump(make_test_manifest(contents=[])))
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


def test_get_image_description_integration(tmp_path):
    image_path = tmp_path / "test.sqfs"
    manifest_path = image_path.with_suffix(".yaml")
    cefs_mount = Path("/fake/cefs")  # Won't be used if manifest exists

    # Test with manifest
    manifest_path.write_text(
        yaml.dump(make_test_manifest(contents=[{"name": "compilers/c++/x86/gcc 11.0.0", "destination": "/opt/gcc-11"}]))
    )
    assert get_image_description(image_path, cefs_mount) == ["compilers/c++/x86/gcc 11.0.0"]

    # Test without manifest (will try to mount, which will fail)
    manifest_path.unlink()
    assert get_image_description(image_path, cefs_mount) is None  # Falls back to mounting which fails in test


def test_classify_installable_location_no_symlink_directory_exists(tmp_path):
    dest = tmp_path / "gcc-11"
    dest.mkdir()
    assert classify_installable_location(dest, None) == f"{dest} [directory]"


def test_classify_installable_location_no_symlink_missing(tmp_path):
    dest = tmp_path / "gcc-11"
    assert classify_installable_location(dest, None) == "NOT INSTALLED"


def test_classify_installable_location_symlink_missing_and_dest_missing(tmp_path):
    dest = tmp_path / "gcc-trunk-20250916"
    symlink = tmp_path / "gcc-trunk"
    assert classify_installable_location(dest, symlink) == "NOT INSTALLED"


def test_classify_installable_location_symlink_points_to_this(tmp_path):
    dest = tmp_path / "gcc-trunk-20250916"
    dest.mkdir()
    symlink = tmp_path / "gcc-trunk"
    symlink.symlink_to("gcc-trunk-20250916")
    result = classify_installable_location(dest, symlink)
    assert result == f"{symlink} -> gcc-trunk-20250916"


def test_classify_installable_location_symlink_superseded(tmp_path):
    # Old dated destination no longer on disk
    dest = tmp_path / "gcc-trunk-20250916"
    # A newer dated dir exists and the un-dated symlink points at it
    newer = tmp_path / "gcc-trunk-20260407"
    newer.mkdir()
    symlink = tmp_path / "gcc-trunk"
    symlink.symlink_to("gcc-trunk-20260407")
    result = classify_installable_location(dest, symlink)
    assert result == f"{symlink} -> gcc-trunk-20260407 (this image: gcc-trunk-20250916, superseded)"


@dataclass
class _FakeInstallable:
    name: str
    path_name_symlink: str | None = None
    install_path_symlink: str | None = None


def test_get_installable_current_locations_uses_installable_lookup(tmp_path):
    image_path = tmp_path / "test.sqfs"
    manifest_path = image_path.with_suffix(".yaml")

    dest = tmp_path / "gcc-trunk-20250916"
    newer = tmp_path / "gcc-trunk-20260407"
    newer.mkdir()
    symlink = tmp_path / "gcc-trunk"
    symlink.symlink_to("gcc-trunk-20260407")

    manifest_path.write_text(
        yaml.dump(make_test_manifest(contents=[{"name": "compilers/c++/x86/gcc trunk", "destination": str(dest)}]))
    )

    installables = {"compilers/c++/x86/gcc trunk": _FakeInstallable("compilers/c++/x86/gcc trunk", "gcc-trunk")}
    lines = get_installable_current_locations(image_path, installables, tmp_path)
    assert len(lines) == 1
    assert "superseded" in lines[0]
    assert "NOT INSTALLED" not in lines[0]


def test_get_installable_current_locations_unknown_installable(tmp_path):
    image_path = tmp_path / "test.sqfs"
    manifest_path = image_path.with_suffix(".yaml")
    manifest_path.write_text(
        yaml.dump(
            make_test_manifest(
                contents=[{"name": "compilers/c++/x86/gcc 11.0.0", "destination": str(tmp_path / "gcc-11")}]
            )
        )
    )
    # Lookup map is empty: falls back to destination check, which is NOT INSTALLED.
    lines = get_installable_current_locations(image_path, {}, tmp_path)
    assert len(lines) == 1
    assert "NOT INSTALLED" in lines[0]


def test_get_installable_current_locations_no_lookup(tmp_path):
    image_path = tmp_path / "test.sqfs"
    manifest_path = image_path.with_suffix(".yaml")
    manifest_path.write_text(
        yaml.dump(
            make_test_manifest(
                contents=[{"name": "compilers/c++/x86/gcc 11.0.0", "destination": str(tmp_path / "gcc-11")}]
            )
        )
    )
    lines = get_installable_current_locations(image_path)
    assert len(lines) == 1
    assert "NOT INSTALLED" in lines[0]
