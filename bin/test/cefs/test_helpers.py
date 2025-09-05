#!/usr/bin/env python3
"""Helper functions for CEFS tests."""

from __future__ import annotations

import datetime
from pathlib import Path

import yaml


def make_test_manifest(**kwargs) -> dict:
    """Create a test manifest with sensible defaults.

    Args:
        **kwargs: Override any default manifest fields

    Returns:
        Complete manifest dictionary
    """
    defaults = {
        "version": 1,
        "operation": "install",
        "description": "Test manifest",
        "contents": [],
        "created_at": datetime.datetime.now(datetime.UTC).isoformat(),
        "git_sha": "test_sha",
        "command": ["test", "command"],
    }
    defaults.update(kwargs)
    return defaults


def write_manifest_alongside_image(manifest: dict, image_path: Path) -> None:
    """Write a manifest file alongside an image file.

    Args:
        manifest: Manifest dictionary to write
        image_path: Path to the image file
    """
    manifest_path = image_path.with_suffix(".yaml")
    with open(manifest_path, "w") as f:
        yaml.dump(manifest, f)


def write_manifest_inprogress(manifest: dict, image_path: Path) -> None:
    """Write an in-progress manifest file.

    Args:
        manifest: Manifest dictionary to write
        image_path: Path to the image file
    """
    inprogress_path = Path(str(image_path.with_suffix(".yaml")) + ".inprogress")
    with open(inprogress_path, "w") as f:
        yaml.dump(manifest, f)
