from __future__ import annotations

import stat
import tempfile
from pathlib import Path

from lib.installation_context import fix_permissions


def test_fix_permissions_skips_broken_symlinks():
    """Test that _fix_permissions handles broken symlinks gracefully."""
    # Create a temporary directory for testing
    with tempfile.TemporaryDirectory() as temp_dir:
        test_dir = Path(temp_dir)

        # Create a regular file
        regular_file = test_dir / "regular.txt"
        regular_file.write_text("test")

        # Create a broken symlink
        broken_link = test_dir / "broken_link"
        broken_link.symlink_to("non_existent_target")

        # Verify the symlink is indeed broken
        assert broken_link.is_symlink()
        assert not broken_link.exists()

        # This should not raise an exception
        fix_permissions(test_dir)

        # Verify the regular file still exists
        assert regular_file.exists()
        # Verify the broken symlink still exists
        assert broken_link.is_symlink()


def test_fix_permissions_handles_valid_symlinks():
    """Test that _fix_permissions handles valid symlinks gracefully."""
    # Create a temporary directory for testing
    with tempfile.TemporaryDirectory() as temp_dir:
        test_dir = Path(temp_dir)

        # Create a target file
        target_file = test_dir / "target.txt"
        target_file.write_text("target content")

        # Create a valid symlink
        valid_link = test_dir / "valid_link"
        valid_link.symlink_to(target_file)

        # Verify the symlink is valid
        assert valid_link.is_symlink()
        assert valid_link.exists()

        # This should not raise an exception
        fix_permissions(test_dir)

        # Verify both files still exist
        assert target_file.exists()
        assert valid_link.is_symlink()
        assert valid_link.exists()


def test_fix_permissions_fixes_root_directory():
    """Test that _fix_permissions fixes the root directory itself, not just subdirectories.

    This is a regression test for a bug where tarballs with restrictive root directory
    permissions (like Qt 6.10.0 with 700) would create CEFS images that were inaccessible.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        test_dir = Path(temp_dir)

        # Create a subdirectory and file
        subdir = test_dir / "subdir"
        subdir.mkdir()
        test_file = subdir / "test.txt"
        test_file.write_text("test content")

        # Set restrictive permissions on root directory (like Qt's broken tarball)
        test_dir.chmod(0o700)
        subdir.chmod(0o700)
        test_file.chmod(0o600)

        # Verify permissions are restrictive
        assert stat.S_IMODE(test_dir.stat().st_mode) == 0o700
        assert stat.S_IMODE(subdir.stat().st_mode) == 0o700
        assert stat.S_IMODE(test_file.stat().st_mode) == 0o600

        # Fix permissions
        fix_permissions(test_dir)

        # Verify root directory permissions are fixed (should be 755)
        root_mode = stat.S_IMODE(test_dir.stat().st_mode)
        assert root_mode == 0o755, f"Expected 0o755, got {oct(root_mode)}"

        # Verify subdirectory permissions are fixed (should be 755)
        subdir_mode = stat.S_IMODE(subdir.stat().st_mode)
        assert subdir_mode == 0o755, f"Expected 0o755, got {oct(subdir_mode)}"

        # Verify file permissions are fixed (should be 644)
        file_mode = stat.S_IMODE(test_file.stat().st_mode)
        assert file_mode == 0o644, f"Expected 0o644, got {oct(file_mode)}"
