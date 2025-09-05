#!/usr/bin/env python3
"""Tests for CEFS formatting module."""

from __future__ import annotations

from pathlib import Path

import yaml
from lib.cefs.formatting import (
    format_image_contents_string,
    get_image_description,
    get_image_description_from_manifest,
)

from test.cefs_test_helpers import make_test_manifest


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
