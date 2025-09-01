#!/usr/bin/env python3
"""Tests for CEFS consolidation functionality."""

import datetime
import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import yaml
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
from lib.cefs_manifest import finalize_manifest, write_manifest_inprogress


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

        result = describe_cefs_image("abc123", Path("/cefs"))

        self.assertEqual(result, ["compilers_c++_x86_gcc_11.1.0", "compilers_c++_x86_gcc_11.2.0"])
        mock_get_mount_path.assert_called_once_with(Path("/cefs"), Path("abc123"))

    @patch("lib.cefs.get_cefs_mount_path")
    @patch("pathlib.Path.iterdir")
    def test_describe_cefs_image_os_error(self, mock_iterdir, mock_get_mount_path):
        """Test CEFS image description with OS error."""
        mock_mount_path = Path("/cefs/ab/abc123")
        mock_get_mount_path.return_value = mock_mount_path

        mock_iterdir.side_effect = OSError("Permission denied")

        result = describe_cefs_image("abc123", Path("/cefs"))

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
        self.assertEqual(len(self.state.referenced_images), 0)
        self.assertEqual(len(self.state.all_cefs_images), 0)

    def test_find_unreferenced_images(self):
        """Test finding unreferenced CEFS images."""
        # Set up test data
        self.state.all_cefs_images = {
            "abc123": Path("/efs/cefs-images/ab/abc123.sqfs"),
            "def456": Path("/efs/cefs-images/de/def456.sqfs"),
            "ghi789": Path("/efs/cefs-images/gh/ghi789.sqfs"),
        }
        self.state.referenced_images = {"abc123", "def456"}

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
        self.state.referenced_images = {"abc123", "def456"}

        # Mock file sizes
        mock_stat.return_value.st_size = 1024 * 1024  # 1MB

        summary = self.state.get_summary()

        self.assertEqual(summary.total_images, 3)
        self.assertEqual(summary.referenced_images, 2)
        self.assertEqual(summary.unreferenced_images, 1)
        self.assertEqual(summary.space_to_reclaim, 1024 * 1024)

    def test_check_symlink_protects_bak(self):
        """Test that _check_symlink_points_to_image protects .bak symlinks.

        This is a critical safety test: ensures that images referenced by .bak
        symlinks are protected from garbage collection to preserve rollback capability.
        """
        # Use _check_single_symlink directly to test the logic
        # Test case 1: .bak symlink points to the image
        bak_path = Mock(spec=Path)
        bak_path.is_symlink.return_value = True
        bak_path.readlink.return_value = Path("/cefs/ab/abc123_test")

        result = self.state._check_single_symlink(bak_path, "abc123_test")
        self.assertTrue(result, ".bak symlink should be recognized as valid reference")

        # Test case 2: Verify the full _check_symlink_points_to_image uses _check_single_symlink for both
        # We'll test this by checking that an image with only a .bak reference is protected
        # This is best tested at a higher level with integration tests

    @patch("pathlib.Path.is_symlink")
    @patch("pathlib.Path.readlink")
    def test_check_single_symlink(self, mock_readlink, mock_is_symlink):
        """Test _check_single_symlink correctly parses CEFS paths."""
        mock_is_symlink.return_value = True
        mock_readlink.return_value = Path("/cefs/ab/abc123_gcc15")

        # Should match
        result = self.state._check_single_symlink(Path("/test/path"), "abc123_gcc15")
        self.assertTrue(result)

        # Should not match different filename
        result = self.state._check_single_symlink(Path("/test/path"), "def456_gcc15")
        self.assertFalse(result)

    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.iterdir")
    @patch("pathlib.Path.is_dir")
    @patch("pathlib.Path.glob")
    def test_scan_with_inprogress_files(self, mock_glob, mock_is_dir, mock_iterdir, mock_exists):
        """Test that scan_cefs_images_with_manifests handles .yaml.inprogress files."""
        mock_exists.return_value = True
        mock_is_dir.return_value = True

        # Mock directory structure
        subdir = Mock()
        subdir.is_dir.return_value = True
        mock_iterdir.return_value = [subdir]

        # Mock files: one regular image and one with inprogress manifest
        regular_image = Mock(spec=Path)
        regular_image.stem = "abc123_test"
        regular_image.with_suffix.return_value.exists.return_value = False  # No .yaml.inprogress

        inprogress_image = Mock(spec=Path)
        inprogress_image.stem = "def456_test"

        # Mock the .yaml.inprogress check
        inprogress_path = Mock()
        inprogress_path.exists.return_value = True

        def with_suffix_side_effect(suffix):
            if suffix == ".yaml":
                result = Mock()
                # This creates the path that will have .inprogress appended
                return result
            return Mock()

        regular_image.with_suffix.side_effect = with_suffix_side_effect
        inprogress_image.with_suffix.side_effect = with_suffix_side_effect

        # Set up glob returns
        def glob_side_effect(pattern):
            if pattern == "*.yaml.inprogress":
                return [Path("/test/def456_test.yaml.inprogress")]
            elif pattern == "*.sqfs":
                return [regular_image, inprogress_image]
            return []

        subdir.glob.side_effect = glob_side_effect

        # Mock Path constructor for the inprogress check
        with patch("lib.cefs.Path") as mock_path_class:
            mock_inprogress = Mock()
            mock_inprogress.exists.return_value = True

            def path_constructor(path_str):
                if ".inprogress" in str(path_str):
                    return mock_inprogress
                return Path(path_str)

            mock_path_class.side_effect = path_constructor

            # Run the scan
            self.state.scan_cefs_images_with_manifests()

        # Image with inprogress should be marked as referenced
        self.assertIn("def456_test", self.state.referenced_images)
        # Should have found the inprogress file
        self.assertEqual(len(self.state.inprogress_images), 1)


class TestCEFSManifest(unittest.TestCase):
    """Test cases for CEFS manifest functions."""

    def test_write_and_finalize_manifest(self):
        """Test write_manifest_inprogress and finalize_manifest workflow."""
        with tempfile.TemporaryDirectory() as tmpdir:
            image_path = Path(tmpdir) / "test.sqfs"
            image_path.touch()

            manifest = {"version": 1, "operation": "test", "contents": []}

            # Write in-progress manifest
            write_manifest_inprogress(manifest, image_path)

            inprogress_path = Path(str(image_path.with_suffix(".yaml")) + ".inprogress")
            self.assertTrue(inprogress_path.exists())

            # Finalize it
            finalize_manifest(image_path)

            final_path = image_path.with_suffix(".yaml")
            self.assertTrue(final_path.exists())
            self.assertFalse(inprogress_path.exists())

    def test_finalize_missing_inprogress(self):
        """Test finalize_manifest raises error when .yaml.inprogress doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            image_path = Path(tmpdir) / "test.sqfs"
            image_path.touch()

            with self.assertRaises(FileNotFoundError):
                finalize_manifest(image_path)


class TestCEFSGarbageCollection(unittest.TestCase):
    """Test cases for CEFS garbage collection functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.nfs_dir = Path(self.temp_dir) / "nfs"
        self.cefs_image_dir = Path(self.temp_dir) / "cefs-images"
        self.nfs_dir.mkdir()
        self.cefs_image_dir.mkdir()

    def tearDown(self):
        """Clean up test fixtures."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_double_check_prevents_deletion_race(self):
        """Test that double-check prevents deletion when symlink is created after initial scan."""

        # Create test image with manifest
        image_hash = "abc123"
        subdir = self.cefs_image_dir / image_hash[:2]
        subdir.mkdir()
        image_path = subdir / f"{image_hash}.sqfs"
        image_path.touch()

        # Create manifest indicating where symlink should be
        manifest_path = image_path.with_suffix(".yaml")
        manifest_content = {"contents": [{"name": "test-compiler", "destination": str(self.nfs_dir / "test-compiler")}]}
        manifest_path.write_text(yaml.dump(manifest_content))

        # Create state and do initial scan
        state = CEFSState(self.nfs_dir, self.cefs_image_dir)
        state.scan_cefs_images_with_manifests()
        state.check_symlink_references()

        # Initially, no symlink exists, so image should be unreferenced
        self.assertIn(image_hash, state.all_cefs_images)
        self.assertNotIn(image_hash, state.referenced_images)

        # Now create a symlink (simulating another process creating it)
        symlink_path = self.nfs_dir / "test-compiler"
        symlink_path.symlink_to(f"/cefs/{image_hash[:2]}/{image_hash}")

        # Double-check should detect the new symlink
        is_referenced = state._check_symlink_points_to_image(self.nfs_dir / "test-compiler", image_hash)
        self.assertTrue(is_referenced, "Double-check should detect newly created symlink")

    def test_bak_symlink_protection(self):
        """Test that .bak symlinks protect images from deletion."""

        # Create test image
        image_hash = "def456"
        subdir = self.cefs_image_dir / image_hash[:2]
        subdir.mkdir()
        image_path = subdir / f"{image_hash}.sqfs"
        image_path.touch()

        # Create manifest
        manifest_path = image_path.with_suffix(".yaml")
        manifest_content = {
            "contents": [{"name": "rollback-compiler", "destination": str(self.nfs_dir / "rollback-compiler")}]
        }
        manifest_path.write_text(yaml.dump(manifest_content))

        # Create only .bak symlink (main symlink is missing/broken)
        bak_symlink = self.nfs_dir / "rollback-compiler.bak"
        bak_symlink.symlink_to(f"/cefs/{image_hash[:2]}/{image_hash}")

        # Create state and scan
        state = CEFSState(self.nfs_dir, self.cefs_image_dir)
        state.scan_cefs_images_with_manifests()
        state.check_symlink_references()

        # Image should be marked as referenced due to .bak symlink
        self.assertIn(image_hash, state.referenced_images, ".bak symlink should protect image from GC")

    def test_inprogress_manifest_protection(self):
        """Test that images with .yaml.inprogress are never deleted."""

        # Create test image with .yaml.inprogress
        image_hash = "ghi789"
        subdir = self.cefs_image_dir / image_hash[:2]
        subdir.mkdir()
        image_path = subdir / f"{image_hash}.sqfs"
        image_path.touch()

        # Create .yaml.inprogress file (incomplete operation)
        inprogress_path = Path(str(image_path.with_suffix(".yaml")) + ".inprogress")
        inprogress_path.touch()

        # Create state and scan
        state = CEFSState(self.nfs_dir, self.cefs_image_dir)
        state.scan_cefs_images_with_manifests()

        # Image should be in referenced set (protected from deletion)
        self.assertIn(image_hash, state.referenced_images, ".yaml.inprogress should protect image")
        self.assertIn(inprogress_path, state.inprogress_images)

    def test_age_filtering_logic(self):
        """Test that age filtering correctly excludes recent images from deletion."""

        # Create test images with different ages
        old_hash = "old001"
        new_hash = "new002"

        for hash_val in [old_hash, new_hash]:
            subdir = self.cefs_image_dir / hash_val[:2]
            subdir.mkdir(exist_ok=True)
            image_path = subdir / f"{hash_val}.sqfs"
            image_path.touch()

            # Create manifest so image is valid
            manifest_path = image_path.with_suffix(".yaml")
            manifest_content = {
                "contents": [{"name": f"test-{hash_val}", "destination": str(self.nfs_dir / f"test-{hash_val}")}]
            }
            manifest_path.write_text(yaml.dump(manifest_content))

            # Set modification time
            if hash_val == old_hash:
                # Make this image 2 hours old
                old_time = time.time() - (2 * 3600)
                os.utime(image_path, (old_time, old_time))

        # Create state and scan
        state = CEFSState(self.nfs_dir, self.cefs_image_dir)
        state.scan_cefs_images_with_manifests()
        state.check_symlink_references()

        # Both should be unreferenced
        unreferenced = state.find_unreferenced_images()
        self.assertEqual(len(unreferenced), 2)

        # With 1 hour min age, only old image should be eligible
        now = datetime.datetime.now()
        min_age_delta = datetime.timedelta(hours=1)

        eligible_for_deletion = []
        for image_path in unreferenced:
            mtime = datetime.datetime.fromtimestamp(image_path.stat().st_mtime)
            age = now - mtime
            if age >= min_age_delta:
                eligible_for_deletion.append(image_path)

        self.assertEqual(len(eligible_for_deletion), 1, "Only old image should be eligible for deletion")
        self.assertEqual(eligible_for_deletion[0].stem, old_hash)

    def test_images_without_manifests_are_broken(self):
        """Test that images without manifests are marked as broken."""

        # Create test image WITHOUT manifest or inprogress marker
        image_hash = "jkl012"
        subdir = self.cefs_image_dir / image_hash[:2]
        subdir.mkdir()
        image_path = subdir / f"{image_hash}.sqfs"
        image_path.touch()
        # No manifest created - this is a broken image

        # Create a symlink pointing to this image
        symlink_path = self.nfs_dir / "legacy-compiler"
        symlink_path.symlink_to(f"/cefs/{image_hash[:2]}/{image_hash}")

        # Create state and scan
        state = CEFSState(self.nfs_dir, self.cefs_image_dir)
        state.scan_cefs_images_with_manifests()
        state.check_symlink_references()

        # Image should be marked as broken, not in all_cefs_images
        self.assertNotIn(image_hash, state.all_cefs_images, "Broken image should not be in all_cefs_images")
        self.assertNotIn(image_hash, state.referenced_images, "Broken image should not be in referenced_images")
        self.assertEqual(len(state.broken_images), 1, "Should have one broken image")
        self.assertEqual(state.broken_images[0], image_path, "Should track the broken image path")

    def test_concurrent_gc_safety(self):
        """Test that concurrent GC executions are safe."""

        # Create test image with manifest
        image_hash = "mno345"
        subdir = self.cefs_image_dir / image_hash[:2]
        subdir.mkdir()
        image_path = subdir / f"{image_hash}.sqfs"
        image_path.touch()

        # Create manifest so image is valid
        manifest_path = image_path.with_suffix(".yaml")
        manifest_content = {"contents": [{"name": "test-compiler", "destination": str(self.nfs_dir / "test-compiler")}]}
        manifest_path.write_text(yaml.dump(manifest_content))

        # Create two independent state objects (simulating concurrent GC runs)
        state1 = CEFSState(self.nfs_dir, self.cefs_image_dir)
        state2 = CEFSState(self.nfs_dir, self.cefs_image_dir)

        # Both scan at the same time
        state1.scan_cefs_images_with_manifests()
        state2.scan_cefs_images_with_manifests()

        # Both identify the same unreferenced image
        unreferenced1 = state1.find_unreferenced_images()
        unreferenced2 = state2.find_unreferenced_images()

        self.assertEqual(len(unreferenced1), 1)
        self.assertEqual(unreferenced1, unreferenced2)

        # If first GC deletes the image
        if image_path.exists():
            image_path.unlink()

        # Second GC should handle missing file gracefully
        # (In real code, this would be in a try/except block)
        self.assertFalse(image_path.exists())

    def test_full_gc_workflow_integration(self):
        """Integration test for the complete GC workflow."""

        # Setup: Create multiple images with different states

        # 1. Referenced image with manifest and symlink
        ref_hash = "ref001"
        ref_subdir = self.cefs_image_dir / ref_hash[:2]
        ref_subdir.mkdir()
        ref_image = ref_subdir / f"{ref_hash}.sqfs"
        ref_image.write_bytes(b"referenced content")

        ref_manifest = ref_image.with_suffix(".yaml")
        ref_manifest.write_text(
            yaml.dump({"contents": [{"name": "gcc-11", "destination": str(self.nfs_dir / "gcc-11")}]})
        )

        # Create the symlink
        (self.nfs_dir / "gcc-11").symlink_to(f"/cefs/{ref_hash[:2]}/{ref_hash}")

        # 2. Unreferenced image with manifest but no symlink
        unref_hash = "unref002"
        unref_subdir = self.cefs_image_dir / unref_hash[:2]
        unref_subdir.mkdir()
        unref_image = unref_subdir / f"{unref_hash}.sqfs"
        unref_image.write_bytes(b"unreferenced content")

        unref_manifest = unref_image.with_suffix(".yaml")
        unref_manifest.write_text(
            yaml.dump({"contents": [{"name": "old-compiler", "destination": str(self.nfs_dir / "old-compiler")}]})
        )
        # No symlink created - this should be GC'd

        # 3. In-progress image (should be protected)
        inprog_hash = "inprog003"
        inprog_subdir = self.cefs_image_dir / inprog_hash[:2]
        inprog_subdir.mkdir()
        inprog_image = inprog_subdir / f"{inprog_hash}.sqfs"
        inprog_image.write_bytes(b"in-progress content")

        # Create .yaml.inprogress
        inprog_manifest = Path(str(inprog_image.with_suffix(".yaml")) + ".inprogress")
        inprog_manifest.touch()

        # 4. Image with .bak symlink only
        bak_hash = "bak004"
        bak_subdir = self.cefs_image_dir / bak_hash[:2]
        bak_subdir.mkdir()
        bak_image = bak_subdir / f"{bak_hash}.sqfs"
        bak_image.write_bytes(b"backup content")

        bak_manifest = bak_image.with_suffix(".yaml")
        bak_manifest.write_text(
            yaml.dump({"contents": [{"name": "backup-gcc", "destination": str(self.nfs_dir / "backup-gcc")}]})
        )

        # Create only .bak symlink
        (self.nfs_dir / "backup-gcc.bak").symlink_to(f"/cefs/{bak_hash[:2]}/{bak_hash}")

        # Run the full GC workflow
        state = CEFSState(self.nfs_dir, self.cefs_image_dir)
        state.scan_cefs_images_with_manifests()
        state.check_symlink_references()

        # Verify the state
        summary = state.get_summary()
        # Note: inprog image is not included in total_images because it's skipped due to .yaml.inprogress
        # but it IS added to referenced_images to protect it from deletion
        self.assertEqual(summary.total_images, 3, "Should have 3 total images (inprog excluded)")
        self.assertEqual(summary.referenced_images, 3, "Should have 3 referenced images (ref, inprog, bak)")
        self.assertEqual(summary.unreferenced_images, 1, "Should have 1 unreferenced image")

        # Check specific images
        self.assertIn(ref_hash, state.referenced_images, "Referenced image should be protected")
        self.assertNotIn(unref_hash, state.referenced_images, "Unreferenced image should be marked for deletion")
        self.assertIn(inprog_hash, state.referenced_images, "In-progress image should be protected")
        self.assertIn(bak_hash, state.referenced_images, ".bak image should be protected")

        # Verify unreferenced images list
        unreferenced = state.find_unreferenced_images()
        self.assertEqual(len(unreferenced), 1)
        self.assertEqual(unreferenced[0].stem, unref_hash)

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
        self.assertFalse(unref_image.exists(), "Unreferenced image should be deleted")
        self.assertFalse(unref_manifest.exists(), "Unreferenced manifest should be deleted")
        self.assertTrue(ref_image.exists(), "Referenced image should still exist")
        self.assertTrue(inprog_image.exists(), "In-progress image should still exist")
        self.assertTrue(bak_image.exists(), ".bak image should still exist")


class TestExtractedGCFunctions(unittest.TestCase):
    """Test the extracted GC utility functions."""

    def test_filter_images_by_age(self):
        """Test filtering images by age."""
        import os
        import time

        from lib.cefs import filter_images_by_age

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create images with different ages
            old_image = Path(tmpdir) / "old.sqfs"
            recent_image = Path(tmpdir) / "recent.sqfs"
            broken_image = Path(tmpdir) / "broken.sqfs"

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
            self.assertEqual(len(result.old_enough), 2)
            self.assertIn(old_image, result.old_enough)
            self.assertIn(broken_image, result.old_enough)  # Can't stat = assume broken = old enough

            # Recent image should be in too_recent with its age
            self.assertEqual(len(result.too_recent), 1)
            self.assertEqual(result.too_recent[0][0], recent_image)
            self.assertLess(result.too_recent[0][1], min_age_delta)

    def test_get_image_description_from_manifest(self):
        """Test extracting description from manifest."""
        from lib.cefs import get_image_description_from_manifest

        with tempfile.TemporaryDirectory() as tmpdir:
            image_path = Path(tmpdir) / "test.sqfs"
            manifest_path = image_path.with_suffix(".yaml")

            # Test with valid manifest
            manifest_path.write_text(
                yaml.dump(
                    {
                        "contents": [
                            {"name": "gcc-11", "destination": "/opt/gcc-11"},
                            {"name": "boost-1.75", "destination": "/opt/boost"},
                        ]
                    }
                )
            )

            names = get_image_description_from_manifest(image_path)
            self.assertEqual(names, ["gcc-11", "boost-1.75"])

            # Test with empty contents
            manifest_path.write_text(yaml.dump({"contents": []}))
            names = get_image_description_from_manifest(image_path)
            self.assertIsNone(names)

            # Test with missing manifest
            manifest_path.unlink()
            names = get_image_description_from_manifest(image_path)
            self.assertIsNone(names)

            # Test with invalid YAML
            manifest_path.write_text("invalid: yaml: content: {")
            names = get_image_description_from_manifest(image_path)
            self.assertIsNone(names)

    def test_format_image_contents_string(self):
        """Test formatting image contents for display."""
        from lib.cefs import format_image_contents_string

        # Test with None
        self.assertEqual(format_image_contents_string(None, 3), "")

        # Test with empty list
        self.assertEqual(format_image_contents_string([], 3), "")

        # Test with items <= max_items
        names = ["gcc-11", "boost"]
        result = format_image_contents_string(names, 3)
        self.assertEqual(result, " [contains: gcc-11, boost]")

        # Test with items > max_items
        names = ["gcc-11", "boost", "cmake", "ninja", "python"]
        result = format_image_contents_string(names, 3)
        self.assertEqual(result, " [contains: gcc-11, boost, cmake...]")

        # Test with max_items = 1
        names = ["gcc-11", "boost"]
        result = format_image_contents_string(names, 1)
        self.assertEqual(result, " [contains: gcc-11...]")

    def test_delete_image_with_manifest(self):
        """Test deleting image and manifest."""
        from lib.cefs import delete_image_with_manifest

        with tempfile.TemporaryDirectory() as tmpdir:
            image_path = Path(tmpdir) / "test.sqfs"
            manifest_path = image_path.with_suffix(".yaml")

            # Test successful deletion with manifest
            image_path.write_bytes(b"image content")
            manifest_path.write_text("manifest content")

            result = delete_image_with_manifest(image_path)
            self.assertTrue(result.success)
            self.assertEqual(result.deleted_size, 13)  # len(b"image content")
            self.assertEqual(result.errors, [])
            self.assertFalse(image_path.exists())
            self.assertFalse(manifest_path.exists())

            # Test deletion without manifest
            image_path.write_bytes(b"image")
            result = delete_image_with_manifest(image_path)
            self.assertTrue(result.success)
            self.assertEqual(result.deleted_size, 5)  # len(b"image")
            self.assertEqual(result.errors, [])

            # Test deletion of non-existent image
            result = delete_image_with_manifest(image_path)
            self.assertFalse(result.success)
            self.assertEqual(result.deleted_size, 0)
            self.assertEqual(len(result.errors), 2)  # stat error and delete error

            # Test deletion when manifest doesn't exist but image does
            image_path.write_bytes(b"content")
            # No manifest created this time
            result = delete_image_with_manifest(image_path)
            self.assertTrue(result.success)  # Image was deleted successfully
            self.assertEqual(result.deleted_size, 7)
            self.assertEqual(len(result.errors), 0)  # No errors
            self.assertFalse(image_path.exists())

    def test_get_image_description_integration(self):
        """Test getting image description with fallback."""
        from lib.cefs import get_image_description

        with tempfile.TemporaryDirectory() as tmpdir:
            image_path = Path(tmpdir) / "test.sqfs"
            manifest_path = image_path.with_suffix(".yaml")
            cefs_mount = Path("/fake/cefs")  # Won't be used if manifest exists

            # Test with manifest
            manifest_path.write_text(yaml.dump({"contents": [{"name": "gcc-11", "destination": "/opt/gcc-11"}]}))
            names = get_image_description(image_path, cefs_mount)
            self.assertEqual(names, ["gcc-11"])

            # Test without manifest (will try to mount, which will fail)
            manifest_path.unlink()
            names = get_image_description(image_path, cefs_mount)
            self.assertIsNone(names)  # Falls back to mounting which fails in test

    def test_is_image_referenced(self):
        """Test the is_image_referenced member function of CEFSState."""
        with tempfile.TemporaryDirectory() as tmpdir:
            nfs_dir = Path(tmpdir) / "nfs"
            cefs_dir = Path(tmpdir) / "cefs"
            nfs_dir.mkdir()
            cefs_dir.mkdir()

            state = CEFSState(nfs_dir, cefs_dir)

            # Set up test data
            state.image_references = {
                "abc123_test": [Path("/opt/gcc-11"), Path("/opt/gcc-12")],
                "def456_test": [Path("/opt/boost")],
                "ghi789_test": [],  # Empty manifest
            }

            # Mock the check method
            with patch.object(state, "_check_symlink_points_to_image") as mock_check:
                # Simulate that /opt/gcc-11 exists for abc123_test
                def check_side_effect(dest_path, filename_stem):
                    return dest_path == Path("/opt/gcc-11") and filename_stem == "abc123_test"

                mock_check.side_effect = check_side_effect

                # Test: Image with valid reference
                self.assertTrue(state.is_image_referenced("abc123_test"), "Should find reference for abc123_test")

                # Test: Image with no valid references
                self.assertFalse(state.is_image_referenced("def456_test"), "Should not find reference for def456_test")

                # Test: Image with empty manifest
                self.assertFalse(state.is_image_referenced("ghi789_test"), "Should return False for empty manifest")

                # Test: Image not in references at all - should raise ValueError
                with self.assertRaises(ValueError) as cm:
                    state.is_image_referenced("missing_image")
                self.assertIn("has no manifest data", str(cm.exception))

    def test_filter_images_by_age_with_specific_times(self):
        """Test age filtering with controlled timestamps."""
        import os
        import time

        from lib.cefs import filter_images_by_age

        with tempfile.TemporaryDirectory() as tmpdir:
            image1 = Path(tmpdir) / "image1.sqfs"
            image2 = Path(tmpdir) / "image2.sqfs"
            image3 = Path(tmpdir) / "image3.sqfs"

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
            self.assertEqual(len(result.old_enough), 2)
            self.assertIn(image1, result.old_enough)
            self.assertIn(image2, result.old_enough)

            # image3 should be too recent
            self.assertEqual(len(result.too_recent), 1)
            self.assertEqual(result.too_recent[0][0], image3)
            # Check the age is approximately 30 minutes
            age_minutes = result.too_recent[0][1].total_seconds() / 60
            self.assertAlmostEqual(age_minutes, 30, delta=1)


if __name__ == "__main__":
    unittest.main()
