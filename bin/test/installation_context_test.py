from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import Mock

from lib.installation_context import InstallationContext
from lib.library_platform import LibraryPlatform


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

        # Create a mock installation context
        config = Mock()
        ic = InstallationContext(
            destination=test_dir,
            staging_root=test_dir,
            s3_url="",
            dry_run=False,
            is_nightly_enabled=False,
            only_nightly=False,
            cache=None,
            yaml_dir=test_dir,
            allow_unsafe_ssl=False,
            resource_dir=test_dir,
            keep_staging=False,
            check_user="test",
            platform=LibraryPlatform.Linux,
            config=config,
        )

        # This should not raise an exception
        ic._fix_permissions(test_dir)

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

        # Create a mock installation context
        config = Mock()
        ic = InstallationContext(
            destination=test_dir,
            staging_root=test_dir,
            s3_url="",
            dry_run=False,
            is_nightly_enabled=False,
            only_nightly=False,
            cache=None,
            yaml_dir=test_dir,
            allow_unsafe_ssl=False,
            resource_dir=test_dir,
            keep_staging=False,
            check_user="test",
            platform=LibraryPlatform.Linux,
            config=config,
        )

        # This should not raise an exception
        ic._fix_permissions(test_dir)

        # Verify both files still exist
        assert target_file.exists()
        assert valid_link.is_symlink()
        assert valid_link.exists()
