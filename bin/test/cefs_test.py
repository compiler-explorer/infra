#!/usr/bin/env python3
"""Tests for CEFS consolidation functionality."""

import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from lib.cefs import (
    CEFSPaths,
    CEFSState,
    check_temp_space_available,
    describe_cefs_image,
    get_cefs_image_path,
    get_cefs_mount_path,
    get_cefs_paths,
    get_extraction_path_from_symlink,
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
        """Test CEFS image path generation with filename."""
        image_dir = Path("/efs/cefs-images")
        filename = Path("9da642f654bc890a12345678_gcc-15.1.0.sqfs")

        result = get_cefs_image_path(image_dir, filename)
        expected = Path("/efs/cefs-images/9d/9da642f654bc890a12345678_gcc-15.1.0.sqfs")

        self.assertEqual(result, expected)

    def test_get_cefs_mount_path_with_filename(self):
        """Test CEFS image path generation with new filename."""
        filename = Path("9da642f654bc890a12345678_gcc-15.1.0.sqfs")

        result = get_cefs_mount_path(Path("/cefs"), filename)
        expected = Path("/cefs/9d/9da642f654bc890a12345678_gcc-15.1.0")

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

    def test_get_cefs_paths(self):
        """Test the combined get_cefs_paths function."""
        image_dir = Path("/efs/cefs-images")
        mount_point = Path("/cefs")
        filename = Path("9da642f654bc890a12345678_gcc-15.1.0.sqfs")

        result = get_cefs_paths(image_dir, mount_point, filename)

        # Verify the result is a CEFSPaths object
        self.assertIsInstance(result, CEFSPaths)

        # Verify the paths are correct
        expected_image_path = Path("/efs/cefs-images/9d/9da642f654bc890a12345678_gcc-15.1.0.sqfs")
        expected_mount_path = Path("/cefs/9d/9da642f654bc890a12345678_gcc-15.1.0")

        self.assertEqual(result.image_path, expected_image_path)
        self.assertEqual(result.mount_path, expected_mount_path)


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

    @patch("pathlib.Path.glob")
    def test_parse_hierarchical_format(self, mock_glob):
        """Test parsing /cefs/XX/HASH format."""
        cefs_target = Path("/cefs/9d/9da642f6a4675f8305f992c02fd9cd019555cbfc2f00c4ba6f8110759aba43f9")

        # Mock that there's a matching file with the new naming convention
        mock_glob.return_value = [
            Path(
                "/efs/cefs-images/9d/9da642f6a4675f8305f992c02fd9cd019555cbfc2f00c4ba6f8110759aba43f9_some_suffix.sqfs"
            )
        ]

        image_path, is_consolidated = parse_cefs_target(cefs_target, self.cefs_image_dir)

        expected_path = Path(
            "/efs/cefs-images/9d/9da642f6a4675f8305f992c02fd9cd019555cbfc2f00c4ba6f8110759aba43f9_some_suffix.sqfs"
        )
        self.assertEqual(image_path, expected_path)
        self.assertFalse(is_consolidated)

    @patch("pathlib.Path.glob")
    def test_parse_consolidated_format(self, mock_glob):
        """Test parsing /cefs/XX/HASH/subdir format."""
        cefs_target = Path("/cefs/ab/abcdef123456789/gcc-4.5.4")

        # Mock that there's a matching consolidated file
        mock_glob.return_value = [Path("/efs/cefs-images/ab/abcdef123456789_consolidated.sqfs")]

        image_path, is_consolidated = parse_cefs_target(cefs_target, self.cefs_image_dir)

        expected_path = Path("/efs/cefs-images/ab/abcdef123456789_consolidated.sqfs")
        self.assertEqual(image_path, expected_path)
        self.assertTrue(is_consolidated)

    @patch("pathlib.Path.glob")
    def test_parse_deeply_nested_consolidated(self, mock_glob):
        """Test parsing /cefs/XX/HASH/deep/sub/dir format."""
        cefs_target = Path("/cefs/cd/cdef456789abc/some-lib/v1.2/bin")

        # Mock that there's a matching consolidated file
        mock_glob.return_value = [Path("/efs/cefs-images/cd/cdef456789abc_consolidated.sqfs")]

        image_path, is_consolidated = parse_cefs_target(cefs_target, self.cefs_image_dir)

        expected_path = Path("/efs/cefs-images/cd/cdef456789abc_consolidated.sqfs")
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

    @patch("pathlib.Path.glob")
    def test_parse_real_gcc_assertions_example(self, mock_glob):
        """Test with real gcc-assertions symlink target."""
        cefs_target = Path("/cefs/9d/9da642f6a4675f8305f992c02fd9cd019555cbfc2f00c4ba6f8110759aba43f9")

        # Mock that there's a matching file with gcc-assertions suffix
        mock_glob.return_value = [
            Path(
                "/efs/cefs-images/9d/9da642f6a4675f8305f992c02fd9cd019555cbfc2f00c4ba6f8110759aba43f9_gcc-assertions.sqfs"
            )
        ]

        image_path, is_consolidated = parse_cefs_target(cefs_target, self.cefs_image_dir)

        expected_path = Path(
            "/efs/cefs-images/9d/9da642f6a4675f8305f992c02fd9cd019555cbfc2f00c4ba6f8110759aba43f9_gcc-assertions.sqfs"
        )
        self.assertEqual(image_path, expected_path)
        self.assertFalse(is_consolidated)


class TestDescribeCefsImage(unittest.TestCase):
    """Test cases for describe_cefs_image function."""

    @patch("lib.cefs.get_cefs_mount_path")
    @patch("pathlib.Path.iterdir")
    def test_describe_cefs_image_success(self, mock_iterdir, mock_get_mount_path):
        """Test successful CEFS image description."""
        mock_mount_path = Path("/cefs/ab/abc123")
        mock_get_mount_path.return_value = mock_mount_path

        # Mock directory entries
        entry1 = Mock()
        entry1.name = "compilers_c++_x86_gcc_11.1.0"
        entry2 = Mock()
        entry2.name = "compilers_c++_x86_gcc_11.2.0"

        mock_iterdir.return_value = [entry1, entry2]

        result = describe_cefs_image("abc123")

        self.assertEqual(result, ["compilers_c++_x86_gcc_11.1.0", "compilers_c++_x86_gcc_11.2.0"])
        mock_get_mount_path.assert_called_once_with(Path("/cefs"), Path("abc123"))

    @patch("lib.cefs.get_cefs_mount_path")
    @patch("pathlib.Path.iterdir")
    def test_describe_cefs_image_os_error(self, mock_iterdir, mock_get_mount_path):
        """Test CEFS image description with OS error."""
        mock_mount_path = Path("/cefs/ab/abc123")
        mock_get_mount_path.return_value = mock_mount_path

        mock_iterdir.side_effect = OSError("Permission denied")

        result = describe_cefs_image("abc123")

        self.assertEqual(result, [])

    @patch("lib.cefs.get_cefs_mount_path")
    @patch("pathlib.Path.iterdir")
    def test_describe_cefs_image_custom_mount_point(self, mock_iterdir, mock_get_mount_path):
        """Test CEFS image description with custom mount point."""
        custom_mount = Path("/custom/cefs")
        mock_mount_path = Path("/custom/cefs/ab/abc123")
        mock_get_mount_path.return_value = mock_mount_path

        entry = Mock()
        entry.name = "test_entry"
        mock_iterdir.return_value = [entry]

        result = describe_cefs_image("abc123", custom_mount)

        self.assertEqual(result, ["test_entry"])
        mock_get_mount_path.assert_called_once_with(custom_mount, Path("abc123"))


class TestCEFSState(unittest.TestCase):
    """Test cases for CEFS garbage collection state tracking."""

    def setUp(self):
        """Set up test fixtures."""
        self.nfs_dir = Path("/opt/compiler-explorer")
        self.cefs_image_dir = Path("/efs/cefs-images")
        self.state = CEFSState(self.nfs_dir, self.cefs_image_dir)

    def test_init(self):
        """Test CEFSState initialization."""
        self.assertEqual(self.state.nfs_dir, self.nfs_dir)
        self.assertEqual(self.state.cefs_image_dir, self.cefs_image_dir)
        self.assertEqual(len(self.state.referenced_hashes), 0)
        self.assertEqual(len(self.state.all_cefs_images), 0)

    @patch("pathlib.Path.is_symlink")
    @patch("pathlib.Path.readlink")
    def test_check_path_for_cefs_symlink(self, mock_readlink, mock_is_symlink):
        """Test CEFS symlink detection."""
        mock_is_symlink.return_value = True
        mock_readlink.return_value = Path("/cefs/ab/abc123def456")

        test_path = Path("/opt/compiler-explorer/gcc-11.1.0")
        self.state._check_path_for_cefs(test_path, "gcc-11.1.0")

        self.assertIn("abc123def456", self.state.referenced_hashes)

    @patch("pathlib.Path.is_symlink")
    @patch("pathlib.Path.readlink")
    def test_check_path_for_non_cefs_symlink(self, mock_readlink, mock_is_symlink):
        """Test non-CEFS symlink handling."""
        mock_is_symlink.return_value = True
        mock_readlink.return_value = Path("/somewhere/else")

        test_path = Path("/opt/compiler-explorer/some-tool")
        self.state._check_path_for_cefs(test_path, "some-tool")

        self.assertEqual(len(self.state.referenced_hashes), 0)

    @patch("pathlib.Path.is_symlink")
    def test_check_path_for_regular_file(self, mock_is_symlink):
        """Test regular file/directory handling."""
        mock_is_symlink.return_value = False

        test_path = Path("/opt/compiler-explorer/regular-dir")
        self.state._check_path_for_cefs(test_path, "regular-dir")

        self.assertEqual(len(self.state.referenced_hashes), 0)

    @patch("pathlib.Path.is_symlink")
    @patch("pathlib.Path.readlink")
    def test_check_path_for_broken_symlink(self, mock_readlink, mock_is_symlink):
        """Test broken symlink handling."""
        mock_is_symlink.return_value = True
        mock_readlink.side_effect = OSError("No such file or directory")

        test_path = Path("/opt/compiler-explorer/broken-link")
        self.state._check_path_for_cefs(test_path, "broken-link")

        self.assertEqual(len(self.state.referenced_hashes), 0)

    def test_scan_installables(self):
        """Test scanning installables for CEFS references."""
        # Create mock installables
        mock_installable1 = Mock()
        mock_installable1.name = "gcc-11.1.0"
        mock_installable1.install_path = "gcc-11.1.0"

        mock_installable2 = Mock()
        mock_installable2.name = "libraries/c++/boost-1.82.0"
        mock_installable2.install_path = "libraries/c++/boost-1.82.0"

        installables = [mock_installable1, mock_installable2]

        with patch.object(self.state, "_check_path_for_cefs") as mock_check:
            self.state.scan_installables(installables)

            # Should check both main path and .bak path for each installable
            self.assertEqual(mock_check.call_count, 4)

            # Verify the correct paths were checked
            mock_check.assert_any_call(self.nfs_dir / "gcc-11.1.0", "gcc-11.1.0")
            mock_check.assert_any_call(self.nfs_dir / "gcc-11.1.0.bak", "gcc-11.1.0.bak")
            mock_check.assert_any_call(self.nfs_dir / "libraries/c++/boost-1.82.0", "libraries/c++/boost-1.82.0")
            mock_check.assert_any_call(
                self.nfs_dir / "libraries/c++/boost-1.82.0.bak", "libraries/c++/boost-1.82.0.bak"
            )

    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.iterdir")
    def test_scan_cefs_images(self, mock_iterdir, mock_exists):
        """Test scanning CEFS images directory."""
        mock_exists.return_value = True

        # Mock directory structure
        subdir1 = Mock()
        subdir1.is_dir.return_value = True
        subdir1.glob.return_value = [
            Mock(stem="abc123def456", spec=Path),
            Mock(stem="def456ghi789", spec=Path),
        ]

        subdir2 = Mock()
        subdir2.is_dir.return_value = True
        subdir2.glob.return_value = [Mock(stem="ghi789jkl012", spec=Path)]

        mock_iterdir.return_value = [subdir1, subdir2]

        self.state.scan_cefs_images()

        self.assertEqual(len(self.state.all_cefs_images), 3)
        self.assertIn("abc123def456", self.state.all_cefs_images)
        self.assertIn("def456ghi789", self.state.all_cefs_images)
        self.assertIn("ghi789jkl012", self.state.all_cefs_images)

    @patch("pathlib.Path.exists")
    def test_scan_cefs_images_missing_dir(self, mock_exists):
        """Test scanning when CEFS images directory doesn't exist."""
        mock_exists.return_value = False

        self.state.scan_cefs_images()

        self.assertEqual(len(self.state.all_cefs_images), 0)

    def test_find_unreferenced_images(self):
        """Test finding unreferenced CEFS images."""
        # Set up test data
        self.state.all_cefs_images = {
            "abc123": Path("/efs/cefs-images/ab/abc123.sqfs"),
            "def456": Path("/efs/cefs-images/de/def456.sqfs"),
            "ghi789": Path("/efs/cefs-images/gh/ghi789.sqfs"),
        }
        self.state.referenced_hashes = {"abc123", "def456"}

        unreferenced = self.state.find_unreferenced_images()

        self.assertEqual(len(unreferenced), 1)
        self.assertEqual(unreferenced[0], Path("/efs/cefs-images/gh/ghi789.sqfs"))

    @patch("pathlib.Path.stat")
    def test_get_summary(self, mock_stat):
        """Test getting summary statistics."""
        # Set up test data
        self.state.all_cefs_images = {
            "abc123": Path("/efs/cefs-images/ab/abc123.sqfs"),
            "def456": Path("/efs/cefs-images/de/def456.sqfs"),
            "ghi789": Path("/efs/cefs-images/gh/ghi789.sqfs"),
        }
        self.state.referenced_hashes = {"abc123", "def456"}

        # Mock file sizes
        mock_stat.return_value.st_size = 1024 * 1024  # 1MB

        summary = self.state.get_summary()

        self.assertEqual(summary["total_images"], 3)
        self.assertEqual(summary["referenced_images"], 2)
        self.assertEqual(summary["unreferenced_images"], 1)
        self.assertEqual(summary["space_to_reclaim"], 1024 * 1024)


if __name__ == "__main__":
    unittest.main()
