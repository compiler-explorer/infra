from __future__ import annotations

import hashlib
import io
import stat
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from lib.config import Config
from lib.installation_context import ChecksumMismatch, FetchFailure, InstallationContext, fix_permissions, parse_sha256
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


def make_context(s3_bucket: str, s3_dir: str) -> InstallationContext:
    with tempfile.TemporaryDirectory() as temp_dir:
        destination = Path(temp_dir)
        return InstallationContext(
            destination=destination,
            staging_root=destination / "staging",
            s3_bucket=s3_bucket,
            s3_dir=s3_dir,
            dry_run=True,
            is_nightly_enabled=False,
            only_nightly=False,
            cache=None,
            yaml_dir=destination,
            allow_unsafe_ssl=False,
            resource_dir=destination,
            keep_staging=False,
            check_user="",
            platform=LibraryPlatform.Linux,
            config=Config(),
        )


def test_s3_url_follows_the_bucket_and_directory():
    assert make_context("compiler-explorer", "opt").s3_url == "https://s3.amazonaws.com/compiler-explorer/opt"
    assert make_context("other-bucket", "opt-nonfree").s3_url == "https://s3.amazonaws.com/other-bucket/opt-nonfree"


PAYLOAD = b"a" * 10 + b"b" * 10
PAYLOAD_SHA256 = hashlib.sha256(PAYLOAD).hexdigest()


def make_fetching_context(payload: bytes) -> InstallationContext:
    context = make_context("compiler-explorer", "opt")
    response = MagicMock(ok=True, headers={"content-length": str(len(payload))})
    response.iter_content.return_value = [payload[:7], payload[7:]]
    context.fetcher = MagicMock()
    context.fetcher.get.return_value = response
    return context


def test_fetch_to_accepts_a_matching_sha256():
    fd = io.BytesIO()
    make_fetching_context(PAYLOAD).fetch_to("https://example.com/x.tar.gz", fd, sha256=PAYLOAD_SHA256)
    assert fd.getvalue() == PAYLOAD


def test_fetch_to_rejects_a_mismatched_sha256():
    with pytest.raises(ChecksumMismatch, match="expected sha256 0{64}, got " + PAYLOAD_SHA256):
        make_fetching_context(PAYLOAD).fetch_to("https://example.com/x.tar.gz", io.BytesIO(), sha256="0" * 64)


def test_checksum_mismatch_is_a_fetch_failure():
    assert issubclass(ChecksumMismatch, FetchFailure)


def test_fetch_to_without_sha256_does_not_verify():
    fd = io.BytesIO()
    make_fetching_context(PAYLOAD).fetch_to("https://example.com/x.tar.gz", fd)
    assert fd.getvalue() == PAYLOAD


def test_fetch_url_and_pipe_to_does_not_run_the_command_on_mismatch(tmp_path, monkeypatch):
    context = make_fetching_context(PAYLOAD)
    check_call = MagicMock()
    monkeypatch.setattr("lib.installation_context.subprocess.check_call", check_call)
    staging = MagicMock(path=tmp_path)
    with pytest.raises(ChecksumMismatch):
        context.fetch_url_and_pipe_to(staging, "https://example.com/x.tar.gz", ["tar", "zxf", "-"], sha256="0" * 64)
    check_call.assert_not_called()


def test_parse_sha256_normalises_case_and_whitespace():
    assert parse_sha256(f" {PAYLOAD_SHA256.upper()}\n") == PAYLOAD_SHA256


def test_parse_sha256_passes_through_none():
    assert parse_sha256(None) is None


@pytest.mark.parametrize("value", ["", "abc", "g" * 64, "0" * 63, "0" * 65])
def test_parse_sha256_rejects_malformed_digests(value):
    with pytest.raises(ValueError, match="expected 64 hex digits"):
        parse_sha256(value)
