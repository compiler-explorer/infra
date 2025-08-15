#!/usr/bin/env python3
"""Tests for CEFS consolidation functionality."""

import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from lib.cefs import (
    check_temp_space_available,
    parse_cefs_target,
    snapshot_symlink_targets,
    verify_symlinks_unchanged,
)
from lib.cli.cefs import _format_size, _parse_size


class TestCEFSConsolidation(unittest.TestCase):
    """Test cases for CEFS consolidation functions."""

    def test_parse_size_valid_formats(self):
        """Test parsing of valid size strings."""
        # Test GB formats
        self.assertEqual(_parse_size("2GB"), 2 * 1024 * 1024 * 1024)
        self.assertEqual(_parse_size("1.5GB"), int(1.5 * 1024 * 1024 * 1024))

        # Test MB formats
        self.assertEqual(_parse_size("500MB"), 500 * 1024 * 1024)
        self.assertEqual(_parse_size("100.5MB"), int(100.5 * 1024 * 1024))

        # Test KB formats
        self.assertEqual(_parse_size("1024KB"), 1024 * 1024)

        # Test bytes
        self.assertEqual(_parse_size("1024"), 1024)

        # Test case insensitive
        self.assertEqual(_parse_size("2gb"), 2 * 1024 * 1024 * 1024)
        self.assertEqual(_parse_size("500mb"), 500 * 1024 * 1024)

    def test_parse_size_invalid_formats(self):
        """Test parsing of invalid size strings."""
        with self.assertRaises(ValueError):
            _parse_size("invalid")

        with self.assertRaises(ValueError):
            _parse_size("2TB")  # Not supported

        with self.assertRaises(ValueError):
            _parse_size("2.5.3GB")  # Invalid number

    def test_format_size(self):
        """Test formatting of byte sizes to human readable strings."""
        # Test GB
        self.assertEqual(_format_size(2 * 1024 * 1024 * 1024), "2.0GB")
        self.assertEqual(_format_size(int(1.5 * 1024 * 1024 * 1024)), "1.5GB")

        # Test MB
        self.assertEqual(_format_size(500 * 1024 * 1024), "500.0MB")
        self.assertEqual(_format_size(1024 * 1024), "1.0MB")

        # Test KB
        self.assertEqual(_format_size(1024), "1.0KB")
        self.assertEqual(_format_size(500), "500B")

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


class TestCEFSPathParsing(unittest.TestCase):
    """Test cases for CEFS path parsing function."""

    def setUp(self):
        self.cefs_image_dir = Path("/efs/cefs-images")

    def test_parse_hierarchical_format(self):
        """Test parsing /cefs/XX/HASH format."""
        cefs_target = Path("/cefs/9d/9da642f6a4675f8305f992c02fd9cd019555cbfc2f00c4ba6f8110759aba43f9")

        image_path, is_consolidated = parse_cefs_target(cefs_target, self.cefs_image_dir)

        expected_path = Path(
            "/efs/cefs-images/9d/9da642f6a4675f8305f992c02fd9cd019555cbfc2f00c4ba6f8110759aba43f9.sqfs"
        )
        self.assertEqual(image_path, expected_path)
        self.assertFalse(is_consolidated)

    def test_parse_consolidated_format(self):
        """Test parsing /cefs/XX/HASH/subdir format."""
        cefs_target = Path("/cefs/ab/abcdef123456789/gcc-4.5.4")

        image_path, is_consolidated = parse_cefs_target(cefs_target, self.cefs_image_dir)

        expected_path = Path("/efs/cefs-images/ab/abcdef123456789.sqfs")
        self.assertEqual(image_path, expected_path)
        self.assertTrue(is_consolidated)

    def test_parse_deeply_nested_consolidated(self):
        """Test parsing /cefs/XX/HASH/deep/sub/dir format."""
        cefs_target = Path("/cefs/cd/cdef456789abc/some-lib/v1.2/bin")

        image_path, is_consolidated = parse_cefs_target(cefs_target, self.cefs_image_dir)

        expected_path = Path("/efs/cefs-images/cd/cdef456789abc.sqfs")
        self.assertEqual(image_path, expected_path)
        self.assertTrue(is_consolidated)

    def test_parse_invalid_too_short(self):
        """Test parsing invalid format with too few components."""
        cefs_target = Path("/cefs/9d")  # Missing HASH

        with self.assertRaises(ValueError) as cm:
            parse_cefs_target(cefs_target, self.cefs_image_dir)
        self.assertIn("Invalid CEFS target format", str(cm.exception))

    def test_parse_invalid_wrong_prefix(self):
        """Test parsing invalid format with wrong prefix."""
        cefs_target = Path("/invalid/9d/hash123")

        with self.assertRaises(ValueError) as cm:
            parse_cefs_target(cefs_target, self.cefs_image_dir)
        self.assertIn("CEFS target must start with /cefs", str(cm.exception))

    def test_parse_real_gcc_assertions_example(self):
        """Test with real gcc-assertions symlink target."""
        cefs_target = Path("/cefs/9d/9da642f6a4675f8305f992c02fd9cd019555cbfc2f00c4ba6f8110759aba43f9")

        image_path, is_consolidated = parse_cefs_target(cefs_target, self.cefs_image_dir)

        expected_path = Path(
            "/efs/cefs-images/9d/9da642f6a4675f8305f992c02fd9cd019555cbfc2f00c4ba6f8110759aba43f9.sqfs"
        )
        self.assertEqual(image_path, expected_path)
        self.assertFalse(is_consolidated)


if __name__ == "__main__":
    unittest.main()
