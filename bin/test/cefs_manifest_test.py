#!/usr/bin/env python3
"""Tests for CEFS manifest system."""

import datetime
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import yaml
from lib.cefs_manifest import (
    create_manifest,
    extract_installable_info_from_path,
    generate_cefs_filename,
    get_git_sha,
    read_manifest_from_alongside,
    sanitize_path_for_filename,
    write_manifest_alongside_image,
)


class TestCEFSManifest(unittest.TestCase):
    """Test cases for CEFS manifest functionality."""

    def test_sanitize_path_for_filename(self):
        """Test path sanitization for filenames."""
        test_cases = [
            (Path("/opt/compiler-explorer/gcc-15.1.0"), "opt_compiler-explorer_gcc-15.1.0"),
            (Path("libs/fusedkernellibrary/Beta-0.1.9/"), "libs_fusedkernellibrary_Beta-0.1.9"),
            (Path("arm/gcc-10.2.0"), "arm_gcc-10.2.0"),
            (Path("path with spaces"), "path_with_spaces"),
            (Path("path:with:colons"), "path_with_colons"),
        ]

        for input_path, expected in test_cases:
            with self.subTest(input_path=str(input_path)):
                self.assertEqual(sanitize_path_for_filename(input_path), expected)

    def test_generate_cefs_filename(self):
        """Test CEFS filename generation."""
        hash_value = "9da642f654bc890a12345678"

        test_cases = [
            (
                "install",
                Path("/opt/compiler-explorer/gcc-15.1.0"),
                Path("9da642f654bc890a12345678_opt_compiler-explorer_gcc-15.1.0.sqfs"),
            ),
            ("consolidate", None, Path("9da642f654bc890a12345678_consolidated.sqfs")),
            ("convert", Path("arm/gcc-10.2.0.img"), Path("9da642f654bc890a12345678_converted_arm_gcc-10.2.0.sqfs")),
            ("unknown", Path("test"), Path("9da642f654bc890a12345678_test.sqfs")),
        ]

        for operation, path, expected in test_cases:
            with self.subTest(operation=operation, path=path):
                result = generate_cefs_filename(hash_value, operation, path)
                self.assertEqual(result, expected)

    def test_extract_installable_info_from_path(self):
        """Test extraction of installable info from paths."""
        test_cases = [
            (
                "gcc-15.1.0",
                Path("/opt/compiler-explorer/gcc-15.1.0"),
                {"name": "gcc", "target": "15.1.0", "destination": "/opt/compiler-explorer/gcc-15.1.0"},
            ),
            (
                "boost-1.82",
                Path("/opt/libs/boost-1.82"),
                {"name": "boost", "target": "1.82", "destination": "/opt/libs/boost-1.82"},
            ),
            (
                "singlename",
                Path("/opt/singlename"),
                {"name": "singlename", "target": "unknown", "destination": "/opt/singlename"},
            ),
        ]

        for install_path, nfs_path, expected in test_cases:
            with self.subTest(install_path=install_path):
                result = extract_installable_info_from_path(install_path, nfs_path)
                self.assertEqual(result, expected)

    @patch("lib.cefs_manifest.subprocess.run")
    def test_get_git_sha_success(self, mock_run):
        """Test successful git SHA retrieval."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "d8c0bd74f9e5ef47e89d6eefe67414bf6b99e3dd\n"
        mock_run.return_value = mock_result

        # Clear the cache first
        get_git_sha.cache_clear()

        result = get_git_sha()
        self.assertEqual(result, "d8c0bd74f9e5ef47e89d6eefe67414bf6b99e3dd")

        # Test caching - should not call subprocess again
        result2 = get_git_sha()
        self.assertEqual(result2, "d8c0bd74f9e5ef47e89d6eefe67414bf6b99e3dd")
        mock_run.assert_called_once()

    @patch("lib.cefs_manifest.subprocess.run")
    def test_get_git_sha_failure(self, mock_run):
        """Test git SHA retrieval failure."""
        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stderr = "Not a git repository"
        mock_run.return_value = mock_result

        # Clear the cache first
        get_git_sha.cache_clear()

        result = get_git_sha()
        self.assertEqual(result, "unknown")

    def test_create_manifest(self):
        """Test manifest creation."""
        contents = [{"name": "gcc", "target": "15.1.0", "destination": "/opt/compiler-explorer/gcc-15.1.0"}]

        with patch("lib.cefs_manifest.get_git_sha", return_value="test_sha"):
            manifest = create_manifest(
                operation="install",
                description="Test installation",
                contents=contents,
                command=["ce_install", "install", "gcc-15.1.0"],
            )

        self.assertEqual(manifest["version"], 1)
        self.assertEqual(manifest["operation"], "install")
        self.assertEqual(manifest["description"], "Test installation")
        self.assertEqual(manifest["contents"], contents)
        self.assertEqual(manifest["command"], ["ce_install", "install", "gcc-15.1.0"])
        self.assertEqual(manifest["git_sha"], "test_sha")
        self.assertIn("created_at", manifest)

        # Verify created_at is a valid ISO format timestamp
        datetime.datetime.fromisoformat(manifest["created_at"])

    def test_write_and_read_manifest_alongside_image(self):
        """Test writing and reading manifest alongside image."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            image_path = temp_path / "test_image.sqfs"

            # Create dummy image file
            image_path.touch()

            manifest = {"version": 1, "operation": "test", "description": "Test manifest", "contents": []}

            # Write manifest alongside
            write_manifest_alongside_image(manifest, image_path)

            # Read manifest back
            loaded_manifest = read_manifest_from_alongside(image_path)

            self.assertEqual(loaded_manifest, manifest)

    def test_read_manifest_from_alongside_nonexistent(self):
        """Test reading manifest from nonexistent file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            image_path = temp_path / "nonexistent.sqfs"

            result = read_manifest_from_alongside(image_path)
            self.assertIsNone(result)

    def test_read_manifest_from_alongside_invalid_yaml(self):
        """Test reading manifest from invalid YAML file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            image_path = temp_path / "test_image.sqfs"
            manifest_path = image_path.with_suffix(".yaml")

            # Write invalid YAML
            with open(manifest_path, "w", encoding="utf-8") as f:
                f.write("invalid: yaml: content: [")

            with self.assertRaises(yaml.YAMLError):
                read_manifest_from_alongside(image_path)


if __name__ == "__main__":
    unittest.main()
