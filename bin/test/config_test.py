#!/usr/bin/env python3
"""Tests for config module."""

import tempfile
import unittest
from pathlib import Path

import yaml
from lib.config import CefsConfig, Config, SquashfsConfig
from pydantic import ValidationError


class TestConfig(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.config_file = self.temp_dir / "config.yaml"

    def tearDown(self):
        if self.config_file.exists():
            self.config_file.unlink()
        if self.temp_dir.exists():
            self.temp_dir.rmdir()

    def test_default_config(self):
        """Test loading config when no config file exists."""
        config = Config.load(self.config_file)

        # Check squashfs defaults
        self.assertTrue(config.squashfs.traditional_enabled)
        self.assertEqual(config.squashfs.image_dir, Path("/efs/squash-images"))
        self.assertEqual(config.squashfs.compression, "zstd")
        self.assertEqual(config.squashfs.compression_level, 19)
        self.assertEqual(config.squashfs.mksquashfs_path, "/usr/bin/mksquashfs")

        # Check cefs defaults
        self.assertFalse(config.cefs.enabled)
        self.assertEqual(config.cefs.mount_point, "/cefs")
        self.assertEqual(config.cefs.image_dir, Path("/efs/cefs-images"))
        self.assertEqual(config.cefs.local_temp_dir, Path("/tmp/ce-cefs-temp"))

    def test_empty_config_file(self):
        """Test loading empty config file."""
        self.config_file.write_text("")
        config = Config.load(self.config_file)

        # Should use defaults
        self.assertTrue(config.squashfs.traditional_enabled)
        self.assertFalse(config.cefs.enabled)

    def test_partial_config(self):
        """Test loading config with only some values specified."""
        config_data = {"squashfs": {"traditional_enabled": True, "compression_level": 15}}

        with self.config_file.open("w", encoding="utf-8") as f:
            yaml.dump(config_data, f)

        config = Config.load(self.config_file)

        # Check specified values
        self.assertTrue(config.squashfs.traditional_enabled)
        self.assertEqual(config.squashfs.compression_level, 15)

        # Check defaults are preserved
        self.assertEqual(config.squashfs.compression, "zstd")
        self.assertEqual(config.squashfs.image_dir, Path("/efs/squash-images"))
        self.assertFalse(config.cefs.enabled)

    def test_full_config(self):
        """Test loading complete config file."""
        config_data = {
            "squashfs": {
                "traditional_enabled": True,
                "image_dir": "/custom/squash-images",
                "compression": "gzip",
                "compression_level": 9,
                "mksquashfs_path": "/custom/bin/mksquashfs",
            },
            "cefs": {
                "enabled": True,
                "mount_point": "/custom/cefs",
                "image_dir": "/custom/cefs-images",
            },
        }

        with self.config_file.open("w", encoding="utf-8") as f:
            yaml.dump(config_data, f)

        config = Config.load(self.config_file)

        # Check squashfs values
        self.assertTrue(config.squashfs.traditional_enabled)
        self.assertEqual(config.squashfs.image_dir, Path("/custom/squash-images"))
        self.assertEqual(config.squashfs.compression, "gzip")
        self.assertEqual(config.squashfs.compression_level, 9)
        self.assertEqual(config.squashfs.mksquashfs_path, "/custom/bin/mksquashfs")

        # Check cefs values
        self.assertTrue(config.cefs.enabled)
        self.assertEqual(config.cefs.mount_point, "/custom/cefs")
        self.assertEqual(config.cefs.image_dir, Path("/custom/cefs-images"))

    def test_unknown_keys_rejected(self):
        """Test that unknown keys in config are rejected."""
        config_data = {"squashfs": {"traditional_enabled": True, "unknown_key": "should_fail"}}

        with self.config_file.open("w", encoding="utf-8") as f:
            yaml.dump(config_data, f)

        with self.assertRaises(ValidationError) as cm:
            Config.load(self.config_file)

        error_str = str(cm.exception)
        self.assertIn("unknown_key", error_str)
        self.assertIn("Extra inputs are not permitted", error_str)

    def test_unknown_top_level_keys_rejected(self):
        """Test that unknown top-level keys are rejected."""
        config_data = {
            "squashfs": {"traditional_enabled": True},
            "unknown_section": {"some": "value"},
        }

        with self.config_file.open("w", encoding="utf-8") as f:
            yaml.dump(config_data, f)

        with self.assertRaises(ValidationError) as cm:
            Config.load(self.config_file)

        error_str = str(cm.exception)
        self.assertIn("unknown_section", error_str)

    def test_invalid_types(self):
        """Test that invalid types are rejected."""
        config_data = {"squashfs": {"traditional_enabled": "not_a_boolean", "compression_level": "not_an_int"}}

        with self.config_file.open("w", encoding="utf-8") as f:
            yaml.dump(config_data, f)

        with self.assertRaises(ValidationError) as cm:
            Config.load(self.config_file)

        error_str = str(cm.exception)
        self.assertIn("traditional_enabled", error_str)
        self.assertIn("compression_level", error_str)

    def test_path_conversion(self):
        """Test that strings are properly converted to Path objects."""
        config_data = {
            "squashfs": {"image_dir": "/string/path"},
            "cefs": {"image_dir": "/another/string/path"},
        }

        with self.config_file.open("w", encoding="utf-8") as f:
            yaml.dump(config_data, f)

        config = Config.load(self.config_file)

        self.assertIsInstance(config.squashfs.image_dir, Path)
        self.assertEqual(config.squashfs.image_dir, Path("/string/path"))
        self.assertIsInstance(config.cefs.image_dir, Path)
        self.assertEqual(config.cefs.image_dir, Path("/another/string/path"))

    def test_config_immutability(self):
        """Test that config objects are immutable."""
        config = Config.load(self.config_file)

        with self.assertRaises(ValidationError):
            config.squashfs.traditional_enabled = True

        with self.assertRaises(ValidationError):
            config.cefs.enabled = True


class TestSquashfsConfig(unittest.TestCase):
    def test_direct_construction(self):
        """Test creating SquashfsConfig directly."""
        config = SquashfsConfig(traditional_enabled=True, compression="gzip", compression_level=9)

        self.assertTrue(config.traditional_enabled)
        self.assertEqual(config.compression, "gzip")
        self.assertEqual(config.compression_level, 9)
        # Defaults should be preserved
        self.assertEqual(config.image_dir, Path("/efs/squash-images"))
        self.assertEqual(config.mksquashfs_path, "/usr/bin/mksquashfs")

    def test_validation_error_on_unknown_field(self):
        """Test that unknown fields raise ValidationError."""
        with self.assertRaises(ValidationError):
            SquashfsConfig(unknown_field="value")


class TestCefsConfig(unittest.TestCase):
    def test_direct_construction(self):
        """Test creating CefsConfig directly."""
        config = CefsConfig(enabled=True, mount_point="/custom/mount")

        self.assertTrue(config.enabled)
        self.assertEqual(config.mount_point, "/custom/mount")
        # Default should be preserved
        self.assertEqual(config.image_dir, Path("/efs/cefs-images"))


if __name__ == "__main__":
    unittest.main()
