"""Tests for golang_stdlib module."""

from __future__ import annotations

from pathlib import Path
from subprocess import TimeoutExpired
from unittest.mock import patch

from lib.golang_stdlib import (
    DEFAULT_ARCHITECTURES,
    get_arch_marker_file,
    get_go_version,
    go_supports_trimpath,
    is_go_installation,
    is_stdlib_already_built,
)


class TestGetGoVersion:
    """Tests for get_go_version function."""

    @patch("lib.golang_stdlib.subprocess.run")
    def test_parses_standard_version(self, mock_run):
        """Go 1.21.5 should return (1, 21)."""
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "go version go1.21.5 linux/amd64"
        assert get_go_version(Path("/opt/go/bin/go")) == (1, 21)

    @patch("lib.golang_stdlib.subprocess.run")
    def test_parses_old_version(self, mock_run):
        """Go 1.4.1 should return (1, 4)."""
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "go version go1.4.1 linux/amd64"
        assert get_go_version(Path("/opt/go/bin/go")) == (1, 4)

    @patch("lib.golang_stdlib.subprocess.run")
    def test_parses_version_without_patch(self, mock_run):
        """Go 1.13 (no patch) should return (1, 13)."""
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "go version go1.13 linux/amd64"
        assert get_go_version(Path("/opt/go/bin/go")) == (1, 13)

    @patch("lib.golang_stdlib.subprocess.run")
    def test_returns_none_on_failure(self, mock_run):
        mock_run.return_value.returncode = 1
        mock_run.return_value.stdout = ""
        assert get_go_version(Path("/opt/go/bin/go")) is None

    @patch("lib.golang_stdlib.subprocess.run")
    def test_returns_none_on_unparseable_output(self, mock_run):
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "something unexpected"
        assert get_go_version(Path("/opt/go/bin/go")) is None

    @patch("lib.golang_stdlib.subprocess.run")
    def test_returns_none_on_timeout(self, mock_run):
        mock_run.side_effect = TimeoutExpired("go", 30)
        assert get_go_version(Path("/opt/go/bin/go")) is None

    @patch("lib.golang_stdlib.subprocess.run")
    def test_returns_none_on_missing_binary(self, mock_run):
        mock_run.side_effect = OSError("No such file")
        assert get_go_version(Path("/opt/go/bin/go")) is None


class TestGoSupportsTrimpath:
    """Tests for go_supports_trimpath function."""

    @patch("lib.golang_stdlib.get_go_version")
    def test_go_1_13_supports_trimpath(self, mock_version):
        mock_version.return_value = (1, 13)
        assert go_supports_trimpath(Path("/opt/go/bin/go")) is True

    @patch("lib.golang_stdlib.get_go_version")
    def test_go_1_21_supports_trimpath(self, mock_version):
        mock_version.return_value = (1, 21)
        assert go_supports_trimpath(Path("/opt/go/bin/go")) is True

    @patch("lib.golang_stdlib.get_go_version")
    def test_go_1_12_does_not_support_trimpath(self, mock_version):
        mock_version.return_value = (1, 12)
        assert go_supports_trimpath(Path("/opt/go/bin/go")) is False

    @patch("lib.golang_stdlib.get_go_version")
    def test_go_1_4_does_not_support_trimpath(self, mock_version):
        mock_version.return_value = (1, 4)
        assert go_supports_trimpath(Path("/opt/go/bin/go")) is False

    @patch("lib.golang_stdlib.get_go_version")
    def test_unknown_version_defaults_to_true(self, mock_version):
        mock_version.return_value = None
        assert go_supports_trimpath(Path("/opt/go/bin/go")) is True


class TestArchMarkerFile:
    """Tests for get_arch_marker_file function."""

    def test_linux_amd64(self, tmp_path):
        result = get_arch_marker_file(tmp_path, "linux/amd64")
        assert result == tmp_path / ".built_linux_amd64"

    def test_linux_arm64(self, tmp_path):
        result = get_arch_marker_file(tmp_path, "linux/arm64")
        assert result == tmp_path / ".built_linux_arm64"


class TestIsGoInstallation:
    """Tests for is_go_installation function."""

    def test_valid_installation(self, tmp_path):
        go_binary = tmp_path / "go" / "bin" / "go"
        go_binary.parent.mkdir(parents=True)
        go_binary.touch()
        assert is_go_installation(tmp_path) is True

    def test_missing_binary(self, tmp_path):
        assert is_go_installation(tmp_path) is False


class TestIsStdlibAlreadyBuilt:
    """Tests for is_stdlib_already_built function."""

    def test_not_built_when_no_cache_dir(self, tmp_path):
        assert is_stdlib_already_built(tmp_path) is False

    def test_not_built_when_cache_empty(self, tmp_path):
        (tmp_path / "cache").mkdir()
        assert is_stdlib_already_built(tmp_path) is False

    def test_built_when_all_markers_present(self, tmp_path):
        cache = tmp_path / "cache"
        cache.mkdir()
        # Need at least one non-marker file so cache dir is non-empty
        (cache / "somefile").touch()
        for arch in DEFAULT_ARCHITECTURES:
            get_arch_marker_file(cache, arch).write_text("built")
        assert is_stdlib_already_built(tmp_path) is True

    def test_not_built_when_marker_missing(self, tmp_path):
        cache = tmp_path / "cache"
        cache.mkdir()
        (cache / "somefile").touch()
        # Only create marker for first arch
        get_arch_marker_file(cache, DEFAULT_ARCHITECTURES[0]).write_text("built")
        assert is_stdlib_already_built(tmp_path) is False
