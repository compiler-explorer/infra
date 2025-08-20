#!/usr/bin/env python3
"""Tests for CEFS consolidation functionality."""

import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from lib.cefs import (
    check_temp_space_available,
    extract_hash_from_cefs_filename,
    get_cefs_image_path,
    get_extraction_path_from_symlink,
    parse_cefs_filename,
    parse_cefs_target,
    snapshot_symlink_targets,
    verify_symlinks_unchanged,
)


class TestCEFSConsolidation(unittest.TestCase):
    """Test cases for CEFS consolidation functions."""

    @patch("os.statvfs")
    def test_check_temp_space_available(self, mock_statvfs):
        """Test temp space checking."""
        # Mock filesystem stats
        mock_stat = Mock()
        mock_stat.f_bavail = 1000  # Available blocks
        mock_stat.f_frsize = 1024 * 1024  # Block size in bytes (1MB)
        mock_statvfs.return_value = mock_stat

        temp_dir = Path("/tmp/test")

        # Test sufficient space (1000MB available, need 500MB)
        self.assertTrue(check_temp_space_available(temp_dir, 500 * 1024 * 1024))

        # Test insufficient space (1000MB available, need 1500MB)
        self.assertFalse(check_temp_space_available(temp_dir, 1500 * 1024 * 1024))

    @patch("os.statvfs")
    def test_check_temp_space_os_error(self, mock_statvfs):
        """Test temp space checking with OS error."""
        mock_statvfs.side_effect = OSError("Permission denied")

        temp_dir = Path("/invalid/path")
        self.assertFalse(check_temp_space_available(temp_dir, 1024))

    def test_snapshot_symlink_targets(self):
        """Test snapshotting of symlink targets."""
        with patch("pathlib.Path.is_symlink") as mock_is_symlink, patch("pathlib.Path.readlink") as mock_readlink:
            # Setup mock symlinks
            paths = [Path("/opt/ce/gcc-4.5"), Path("/opt/ce/boost-1.82")]
            targets = [Path("/cefs/ab/abc123"), Path("/cefs/cd/cdef456")]

            mock_is_symlink.return_value = True
            mock_readlink.side_effect = targets

            result = snapshot_symlink_targets(paths)

            expected = {paths[0]: targets[0], paths[1]: targets[1]}
            self.assertEqual(result, expected)

    def test_snapshot_symlink_targets_with_errors(self):
        """Test snapshotting with some symlinks having errors."""
        with patch("pathlib.Path.is_symlink") as mock_is_symlink, patch("pathlib.Path.readlink") as mock_readlink:
            paths = [Path("/opt/ce/gcc-4.5"), Path("/opt/ce/boost-1.82")]

            # First symlink works, second fails
            mock_is_symlink.return_value = True
            mock_readlink.side_effect = [Path("/cefs/ab/abc123"), OSError("Permission denied")]

            result = snapshot_symlink_targets(paths)

            # Should only have first symlink
            expected = {paths[0]: Path("/cefs/ab/abc123")}
            self.assertEqual(result, expected)

    def test_verify_symlinks_unchanged(self):
        """Test verification of unchanged symlinks."""
        with patch("pathlib.Path.is_symlink") as mock_is_symlink, patch("pathlib.Path.readlink") as mock_readlink:
            # Setup test data
            paths = [Path("/opt/ce/gcc-4.5"), Path("/opt/ce/boost-1.82")]
            original_targets = [Path("/cefs/ab/abc123"), Path("/cefs/cd/cdef456")]
            current_targets = [Path("/cefs/ab/abc123"), Path("/cefs/ef/efgh789")]  # Second changed

            snapshot = {paths[0]: original_targets[0], paths[1]: original_targets[1]}

            mock_is_symlink.return_value = True
            mock_readlink.side_effect = current_targets

            unchanged, changed = verify_symlinks_unchanged(snapshot)

            self.assertEqual(unchanged, [paths[0]])  # First unchanged
            self.assertEqual(changed, [paths[1]])  # Second changed

    def test_verify_symlinks_nonexistent(self):
        """Test verification when symlink no longer exists."""
        with patch("pathlib.Path.is_symlink") as mock_is_symlink:
            path = Path("/opt/ce/gcc-4.5")
            snapshot = {path: Path("/cefs/ab/abc123")}

            # Symlink no longer exists
            mock_is_symlink.return_value = False

            unchanged, changed = verify_symlinks_unchanged(snapshot)

            self.assertEqual(unchanged, [])
            self.assertEqual(changed, [path])

    def test_get_cefs_image_path_with_filename(self):
        """Test CEFS image path generation with new filename."""
        image_dir = Path("/efs/cefs-images")
        hash_value = "9da642f654bc890a12345678"
        filename = "9da642f654bc890a12345678_gcc-15.1.0.sqfs"

        result = get_cefs_image_path(image_dir, hash_value, filename)
        expected = Path("/efs/cefs-images/9d/9da642f654bc890a12345678_gcc-15.1.0.sqfs")

        self.assertEqual(result, expected)

    def test_parse_cefs_filename(self):
        """Test CEFS filename parsing."""
        test_cases = [
            ("9da642f654bc890a12345678_gcc-15.1.0.sqfs", ("9da642f654bc890a12345678", "install", "gcc-15.1.0")),
            ("abcdef1234567890abcdef12_consolidated.sqfs", ("abcdef1234567890abcdef12", "consolidate", "")),
            (
                "123456789abcdef0123456789_converted_arm_gcc-10.2.0.sqfs",
                ("123456789abcdef0123456789", "convert", "arm_gcc-10.2.0"),
            ),
        ]

        for filename, expected in test_cases:
            with self.subTest(filename=filename):
                result = parse_cefs_filename(filename)
                self.assertEqual(result, expected)

    def test_extract_hash_from_cefs_filename(self):
        """Test hash extraction from CEFS filename."""
        test_cases = [
            ("9da642f654bc890a12345678_gcc-15.1.0.sqfs", "9da642f654bc890a12345678"),
            ("abcdef1234567890abcdef12_consolidated.sqfs", "abcdef1234567890abcdef12"),
            ("legacy_format", "legacy"),  # parse_cefs_filename will split on first underscore
        ]

        for filename, expected in test_cases:
            with self.subTest(filename=filename):
                result = extract_hash_from_cefs_filename(filename)
                self.assertEqual(result, expected)

    @patch("pathlib.Path.glob")
    def test_parse_cefs_target_with_new_naming(self, mock_glob):
        """Test parsing CEFS target with new naming convention."""
        cefs_target = Path("/cefs/9d/9da642f654bc890a12345678")
        cefs_image_dir = Path("/efs/cefs-images")

        # Mock that there's a matching file
        mock_glob.return_value = [Path("/efs/cefs-images/9d/9da642f654bc890a12345678_gcc-15.1.0.sqfs")]

        cefs_image_path, is_consolidated = parse_cefs_target(cefs_target, cefs_image_dir)

        expected_path = Path("/efs/cefs-images/9d/9da642f654bc890a12345678_gcc-15.1.0.sqfs")
        self.assertEqual(cefs_image_path, expected_path)
        self.assertFalse(is_consolidated)

    @patch("pathlib.Path.glob")
    def test_parse_cefs_target_consolidated(self, mock_glob):
        """Test parsing CEFS target for consolidated image."""
        cefs_target = Path("/cefs/ab/abcdef1234567890abcdef12/gcc-4.5")
        cefs_image_dir = Path("/efs/cefs-images")

        # Mock that there's a matching consolidated file
        mock_glob.return_value = [Path("/efs/cefs-images/ab/abcdef1234567890abcdef12_consolidated.sqfs")]

        cefs_image_path, is_consolidated = parse_cefs_target(cefs_target, cefs_image_dir)

        expected_path = Path("/efs/cefs-images/ab/abcdef1234567890abcdef12_consolidated.sqfs")
        self.assertEqual(cefs_image_path, expected_path)
        self.assertTrue(is_consolidated)

    def test_get_extraction_path_from_symlink(self):
        """Test extraction path determination from symlink targets."""
        test_cases = [
            (Path("/cefs/ab/abcdef1234567890abcdef12"), Path(".")),
            (Path("/cefs/ab/abcdef1234567890abcdef12/content"), Path("content")),
            (Path("/cefs/ab/abcdef1234567890abcdef12/gcc-4.5"), Path("gcc-4.5")),
            (Path("/cefs/ab/abcdef1234567890abcdef12/libs/boost"), Path("libs/boost")),
            (Path("/cefs/cd/cdef1234567890123456789/deep/nested/path"), Path("deep/nested/path")),
        ]

        for symlink_target, expected in test_cases:
            with self.subTest(symlink_target=str(symlink_target)):
                result = get_extraction_path_from_symlink(symlink_target)
                self.assertEqual(result, expected)


class TestCEFSConsolidationIntegration(unittest.TestCase):
    """Integration tests for CEFS consolidation."""

    def test_consolidation_grouping_algorithm(self):
        """Test the grouping algorithm used in consolidation."""
        # Simulate the grouping logic from the consolidate command
        items = [
            {"name": "gcc-4.5", "size": 100 * 1024 * 1024},  # 100MB
            {"name": "gcc-4.6", "size": 150 * 1024 * 1024},  # 150MB
            {"name": "gcc-5.1", "size": 200 * 1024 * 1024},  # 200MB
            {"name": "boost-1.82", "size": 300 * 1024 * 1024},  # 300MB
            {"name": "fmt-8.1", "size": 50 * 1024 * 1024},  # 50MB
        ]

        max_size_bytes = 400 * 1024 * 1024  # 400MB max per group
        min_items = 2

        # Sort by name (as in real implementation)
        items.sort(key=lambda x: x["name"])

        # Pack items into groups
        groups = []
        current_group = []
        current_size = 0

        for item in items:
            if current_size + item["size"] > max_size_bytes and len(current_group) >= min_items:
                groups.append(current_group)
                current_group = [item]
                current_size = item["size"]
            else:
                current_group.append(item)
                current_size += item["size"]

        if len(current_group) >= min_items:
            groups.append(current_group)

        # Verify grouping results
        self.assertEqual(len(groups), 2)  # Should create 2 groups

        # First group: boost-1.82 (300MB) + fmt-8.1 (50MB) = 350MB
        self.assertEqual(len(groups[0]), 2)
        self.assertIn("boost-1.82", [item["name"] for item in groups[0]])
        self.assertIn("fmt-8.1", [item["name"] for item in groups[0]])

        # Second group: gcc-4.5 (100MB) + gcc-4.6 (150MB) = 250MB
        # gcc-5.1 (200MB) would exceed 400MB limit, so it starts new group
        self.assertEqual(len(groups[1]), 2)
        self.assertIn("gcc-4.5", [item["name"] for item in groups[1]])
        self.assertIn("gcc-4.6", [item["name"] for item in groups[1]])

    def test_subdirectory_name_generation(self):
        """Test generation of safe subdirectory names."""
        # Test the subdirectory name logic from consolidate command
        test_cases = [
            ("gcc 4.5.4", "gcc_4.5.4"),
            ("compilers/c++/gcc", "compilers_c++_gcc"),
            ("cross/arm/gcc", "cross_arm_gcc"),
            ("boost-1.82.0", "boost-1.82.0"),
        ]

        for input_name, expected_output in test_cases:
            # This is the logic from the consolidate command
            subdir_name = input_name.replace("/", "_").replace(" ", "_")
            self.assertEqual(subdir_name, expected_output)


if __name__ == "__main__":
    unittest.main()
