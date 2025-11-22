"""Tests for golang CLI commands."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, call, mock_open, patch

import pytest

from lib.golang_stdlib import (
    DEFAULT_ARCHITECTURES,
    STDLIB_CACHE_DIR,
    _get_arch_marker_file,
    build_go_stdlib,
    is_go_installation,
    is_stdlib_already_built,
)


class TestIsGoInstallation:
    """Tests for is_go_installation function."""

    def test_valid_go_installation(self, tmp_path: Path):
        """Test detecting a valid Go installation."""
        go_bin = tmp_path / "go" / "bin" / "go"
        go_bin.parent.mkdir(parents=True)
        go_bin.touch()

        assert is_go_installation(tmp_path) is True

    def test_missing_go_binary(self, tmp_path: Path):
        """Test detecting missing Go binary."""
        assert is_go_installation(tmp_path) is False

    def test_go_binary_is_directory(self, tmp_path: Path):
        """Test when go binary path is a directory."""
        go_bin = tmp_path / "go" / "bin" / "go"
        go_bin.mkdir(parents=True)

        assert is_go_installation(tmp_path) is False


class TestIsStdlibAlreadyBuilt:
    """Tests for is_stdlib_already_built function."""

    def test_stdlib_built_with_all_arch_markers(self, tmp_path: Path):
        """Test stdlib is considered built when all arch markers exist."""
        cache_dir = tmp_path / STDLIB_CACHE_DIR
        cache_dir.mkdir()
        (cache_dir / "some_cache_file").touch()

        # Create marker for each default architecture
        for arch in DEFAULT_ARCHITECTURES:
            marker = _get_arch_marker_file(cache_dir, arch)
            marker.write_text("Built")

        assert is_stdlib_already_built(tmp_path) is True

    def test_stdlib_not_built_missing_arch_marker(self, tmp_path: Path):
        """Test stdlib is not considered built if any arch marker is missing."""
        cache_dir = tmp_path / STDLIB_CACHE_DIR
        cache_dir.mkdir()
        (cache_dir / "some_cache_file").touch()

        # Only create marker for first architecture
        marker = _get_arch_marker_file(cache_dir, DEFAULT_ARCHITECTURES[0])
        marker.write_text("Built")

        assert is_stdlib_already_built(tmp_path) is False

    def test_stdlib_not_built_empty_cache(self, tmp_path: Path):
        """Test stdlib is not considered built with empty cache directory."""
        cache_dir = tmp_path / STDLIB_CACHE_DIR
        cache_dir.mkdir()

        # Empty cache directory (no build artifacts or markers)
        assert is_stdlib_already_built(tmp_path) is False

    def test_stdlib_not_built_no_cache_dir(self, tmp_path: Path):
        """Test stdlib is not considered built without cache directory."""
        assert is_stdlib_already_built(tmp_path) is False

    def test_stdlib_custom_architectures(self, tmp_path: Path):
        """Test checking stdlib for custom architectures."""
        cache_dir = tmp_path / STDLIB_CACHE_DIR
        cache_dir.mkdir()
        (cache_dir / "some_cache_file").touch()

        custom_archs = ["linux/amd64", "linux/386"]

        # Create markers for custom architectures
        for arch in custom_archs:
            marker = _get_arch_marker_file(cache_dir, arch)
            marker.write_text("Built")

        assert is_stdlib_already_built(tmp_path, custom_archs) is True
        # But should fail for different architectures
        assert is_stdlib_already_built(tmp_path, ["linux/amd64", "linux/arm64"]) is False


class TestBuildGoStdlib:
    """Tests for build_go_stdlib function."""

    @patch("lib.golang_stdlib.subprocess.run")
    def test_dry_run_mode(self, mock_run: MagicMock, tmp_path: Path):
        """Test dry run mode still builds stdlib."""
        go_bin = tmp_path / "go" / "bin" / "go"
        go_bin.parent.mkdir(parents=True)
        go_bin.touch()

        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        result = build_go_stdlib(tmp_path, dry_run=True)

        assert result is True
        # Verify cache directory WAS created even in dry run
        assert (tmp_path / STDLIB_CACHE_DIR).exists()
        # Verify builds were executed
        assert mock_run.call_count == len(DEFAULT_ARCHITECTURES)

    def test_missing_go_binary_raises_error(self, tmp_path: Path):
        """Test that missing Go binary raises RuntimeError."""
        with pytest.raises(RuntimeError, match="Go binary not found"):
            build_go_stdlib(tmp_path)

    @patch("lib.golang_stdlib.subprocess.run")
    def test_successful_build_single_arch(self, mock_run: MagicMock, tmp_path: Path):
        """Test successful stdlib build for single architecture."""
        go_bin = tmp_path / "go" / "bin" / "go"
        go_bin.parent.mkdir(parents=True)
        go_bin.touch()

        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        result = build_go_stdlib(tmp_path, architectures=["linux/amd64"])

        assert result is True
        assert mock_run.call_count == 1

        # Verify the call was made with correct environment
        call_args = mock_run.call_args
        assert call_args[0][0] == [str(go_bin), "build", "-v", "std"]
        assert call_args[1]["env"]["GOOS"] == "linux"
        assert call_args[1]["env"]["GOARCH"] == "amd64"
        assert call_args[1]["env"]["GOROOT"] == str(tmp_path / "go")
        assert call_args[1]["env"]["GOCACHE"] == str(tmp_path / STDLIB_CACHE_DIR)

        # Verify marker file was created in cache directory
        cache_dir = tmp_path / STDLIB_CACHE_DIR
        marker = _get_arch_marker_file(cache_dir, "linux/amd64")
        assert marker.exists()
        assert marker.name == ".built_linux_amd64"

    @patch("lib.golang_stdlib.subprocess.run")
    def test_successful_build_multiple_archs(self, mock_run: MagicMock, tmp_path: Path):
        """Test successful stdlib build for multiple architectures."""
        go_bin = tmp_path / "go" / "bin" / "go"
        go_bin.parent.mkdir(parents=True)
        go_bin.touch()

        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        result = build_go_stdlib(tmp_path, architectures=["linux/amd64", "linux/arm64"])

        assert result is True
        assert mock_run.call_count == 2

        # Verify both architectures were built
        call_envs = [call_args[1]["env"] for call_args in mock_run.call_args_list]
        assert any(env["GOOS"] == "linux" and env["GOARCH"] == "amd64" for env in call_envs)
        assert any(env["GOOS"] == "linux" and env["GOARCH"] == "arm64" for env in call_envs)

    @patch("lib.golang_stdlib.subprocess.run")
    def test_build_failure(self, mock_run: MagicMock, tmp_path: Path):
        """Test build failure handling."""
        go_bin = tmp_path / "go" / "bin" / "go"
        go_bin.parent.mkdir(parents=True)
        go_bin.touch()

        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="build output",
            stderr="build error",
        )

        result = build_go_stdlib(tmp_path, architectures=["linux/amd64"])

        assert result is False
        # Marker file should not be created on failure
        cache_dir = tmp_path / STDLIB_CACHE_DIR
        marker = _get_arch_marker_file(cache_dir, "linux/amd64")
        assert not marker.exists()

    @patch("lib.golang_stdlib.subprocess.run")
    def test_partial_success(self, mock_run: MagicMock, tmp_path: Path):
        """Test partial success when some architectures fail."""
        go_bin = tmp_path / "go" / "bin" / "go"
        go_bin.parent.mkdir(parents=True)
        go_bin.touch()

        # First call succeeds, second fails
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="", stderr=""),
            MagicMock(returncode=1, stdout="", stderr="error"),
        ]

        result = build_go_stdlib(tmp_path, architectures=["linux/amd64", "linux/arm64"])

        # Should still return True if at least one succeeded
        assert result is True
        assert mock_run.call_count == 2

        # Marker file should be created only for successful architecture
        cache_dir = tmp_path / STDLIB_CACHE_DIR
        marker_amd64 = _get_arch_marker_file(cache_dir, "linux/amd64")
        marker_arm64 = _get_arch_marker_file(cache_dir, "linux/arm64")
        assert marker_amd64.exists()
        assert not marker_arm64.exists()

    @patch("lib.golang_stdlib.subprocess.run")
    def test_invalid_architecture_format(self, mock_run: MagicMock, tmp_path: Path):
        """Test handling of invalid architecture format."""
        go_bin = tmp_path / "go" / "bin" / "go"
        go_bin.parent.mkdir(parents=True)
        go_bin.touch()

        result = build_go_stdlib(tmp_path, architectures=["invalid-arch", "linux/amd64"])

        # Should still attempt valid architecture
        assert mock_run.call_count == 1

        # Should succeed for the valid architecture
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = build_go_stdlib(tmp_path, architectures=["invalid-arch", "linux/amd64"])
        assert result is True

    @patch("lib.golang_stdlib.subprocess.run")
    def test_timeout_handling(self, mock_run: MagicMock, tmp_path: Path):
        """Test handling of build timeout."""
        go_bin = tmp_path / "go" / "bin" / "go"
        go_bin.parent.mkdir(parents=True)
        go_bin.touch()

        mock_run.side_effect = subprocess.TimeoutExpired("go", 600)

        result = build_go_stdlib(tmp_path, architectures=["linux/amd64"])

        assert result is False

    @patch("lib.golang_stdlib.subprocess.run")
    def test_default_architectures_used(self, mock_run: MagicMock, tmp_path: Path):
        """Test that default architectures are used when none specified."""
        go_bin = tmp_path / "go" / "bin" / "go"
        go_bin.parent.mkdir(parents=True)
        go_bin.touch()

        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        build_go_stdlib(tmp_path)  # No architectures specified

        assert mock_run.call_count == len(DEFAULT_ARCHITECTURES)

    @patch("lib.golang_stdlib.subprocess.run")
    def test_cache_directory_created(self, mock_run: MagicMock, tmp_path: Path):
        """Test that cache directory is created."""
        go_bin = tmp_path / "go" / "bin" / "go"
        go_bin.parent.mkdir(parents=True)
        go_bin.touch()

        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        build_go_stdlib(tmp_path, architectures=["linux/amd64"])

        cache_dir = tmp_path / STDLIB_CACHE_DIR
        assert cache_dir.exists()
        assert cache_dir.is_dir()

    @patch("lib.golang_stdlib.subprocess.run")
    def test_custom_cache_directory(self, mock_run: MagicMock, tmp_path: Path):
        """Test that custom cache directory is used when specified."""
        go_bin = tmp_path / "go" / "bin" / "go"
        go_bin.parent.mkdir(parents=True)
        go_bin.touch()

        custom_cache = tmp_path / "my_custom_cache"
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        build_go_stdlib(tmp_path, architectures=["linux/amd64"], cache_dir=custom_cache)

        # Verify custom cache directory was created
        assert custom_cache.exists()
        assert custom_cache.is_dir()

        # Verify GOCACHE was set to custom directory
        call_args = mock_run.call_args
        assert call_args[1]["env"]["GOCACHE"] == str(custom_cache)

        # Verify default cache directory was NOT created
        default_cache = tmp_path / STDLIB_CACHE_DIR
        assert not default_cache.exists()
