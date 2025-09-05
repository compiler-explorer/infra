#!/usr/bin/env python3
"""Tests for CEFS manifest module."""

from __future__ import annotations

import datetime
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import yaml
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

from test.cefs_test_helpers import make_test_manifest


def test_write_and_finalize_manifest(tmp_path):
    """Test write_and_finalize_manifest function."""
    image_path = tmp_path / "test.sqfs"
    image_path.touch()
    manifest = {"test": "data", "contents": [{"name": "test"}]}

    # Write in-progress manifest
    write_manifest_inprogress(manifest, image_path)
    inprogress_path = Path(str(image_path.with_suffix(".yaml")) + ".inprogress")
    assert inprogress_path.exists()

    # Finalize it
    finalize_manifest(image_path)

    manifest_path = image_path.with_suffix(".yaml")
    assert manifest_path.exists()
    with open(manifest_path) as f:
        loaded = yaml.safe_load(f)
    assert loaded == manifest


def test_finalize_missing_inprogress(tmp_path):
    """Test finalize_manifest when .inprogress file doesn't exist."""
    image_path = tmp_path / "test.sqfs"
    image_path.touch()

    # Should raise FileNotFoundError when .inprogress doesn't exist
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


def test_create_installable_manifest_entry():
    """Test create_installable_manifest_entry function."""
    entry = create_installable_manifest_entry("gcc-13.2.0", Path("/opt/gcc"))
    assert entry["name"] == "gcc-13.2.0"
    assert entry["destination"] == "/opt/gcc"


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

    manifest = make_test_manifest()

    # Write manifest alongside
    write_manifest_alongside_image(manifest, image_path)

    # Read manifest back
    loaded_manifest = read_manifest_from_alongside(image_path)

    assert loaded_manifest == manifest


def test_read_manifest_from_alongside_nonexistent():
    """Test read_manifest_from_alongside with nonexistent file."""
    result = read_manifest_from_alongside(Path("/nonexistent/file.sqfs"))
    assert result is None


def test_read_manifest_from_alongside_invalid_yaml(tmp_path):
    image_path = tmp_path / "test_image.sqfs"
    manifest_path = image_path.with_suffix(".yaml")

    # Write invalid YAML
    manifest_path.write_text("invalid: yaml: content: [")

    with pytest.raises(yaml.YAMLError):
        read_manifest_from_alongside(image_path)
