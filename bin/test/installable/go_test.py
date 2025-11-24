"""Tests for Go installable."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from lib.golang_stdlib import DEFAULT_ARCHITECTURES, STDLIB_CACHE_DIR
from lib.installable.go import GoInstallable
from lib.installation_context import InstallationContext


class TestGoInstallable:
    """Tests for GoInstallable class."""

    @pytest.fixture
    def mock_context(self, tmp_path: Path):
        """Create a mock installation context."""
        context = MagicMock(spec=InstallationContext)
        context.destination = tmp_path / "destination"
        context.destination.mkdir(parents=True)
        context.dry_run = False
        return context

    @pytest.fixture
    def basic_config(self):
        """Create basic Go installable config."""
        return {
            "name": "1.24.2",
            "context": ["compilers", "go", "golang"],
            "type": "go",
            "compression": "gz",
            "url": "https://storage.googleapis.com/golang/go1.24.2.linux-amd64.tar.gz",
            "dir": "golang-1.24.2",
            "untar_dir": "golang-1.24.2",
            "create_untar_dir": True,
            "strip": True,
        }

    def test_init_with_defaults(self, mock_context: MagicMock, basic_config: dict):
        """Test GoInstallable initialization with default values."""
        installable = GoInstallable(mock_context, basic_config)

        assert installable.build_stdlib is True
        assert installable.build_stdlib_archs == DEFAULT_ARCHITECTURES
        assert installable.install_path == "golang-1.24.2"

    def test_init_with_custom_archs(self, mock_context: MagicMock, basic_config: dict):
        """Test GoInstallable initialization with custom architectures."""
        basic_config["build_stdlib_archs"] = ["linux/amd64"]

        installable = GoInstallable(mock_context, basic_config)

        assert installable.build_stdlib_archs == ["linux/amd64"]

    def test_init_with_stdlib_disabled(self, mock_context: MagicMock, basic_config: dict):
        """Test GoInstallable initialization with stdlib building disabled."""
        basic_config["build_stdlib"] = False

        installable = GoInstallable(mock_context, basic_config)

        assert installable.build_stdlib is False

    @patch("lib.installable.go.build_go_stdlib")
    @patch.object(GoInstallable.__bases__[0], "stage")
    def test_stage_builds_stdlib(
        self,
        mock_super_stage: MagicMock,
        mock_build_stdlib: MagicMock,
        mock_context: MagicMock,
        basic_config: dict,
        tmp_path: Path,
    ):
        """Test that stage() builds stdlib after calling parent stage()."""
        # Setup
        staging_dir = tmp_path / "staging"
        staging_dir.mkdir()
        go_install_dir = staging_dir / "golang-1.24.2"
        go_install_dir.mkdir()
        (go_install_dir / "go").mkdir()
        (go_install_dir / "go" / "bin").mkdir(parents=True)
        (go_install_dir / "go" / "bin" / "go").touch()

        staging_mock = MagicMock()
        staging_mock.path = staging_dir

        mock_build_stdlib.return_value = True

        installable = GoInstallable(mock_context, basic_config)

        # Execute
        installable.stage(staging_mock)

        # Verify
        mock_super_stage.assert_called_once_with(staging_mock)
        mock_build_stdlib.assert_called_once()

        # Check the arguments passed to build_go_stdlib
        call_kwargs = mock_build_stdlib.call_args[1]
        assert call_kwargs["go_installation_path"] == go_install_dir
        assert call_kwargs["architectures"] == DEFAULT_ARCHITECTURES
        assert call_kwargs["cache_dir"] == go_install_dir / STDLIB_CACHE_DIR
        assert call_kwargs["dry_run"] is False

    @patch("lib.installable.go.build_go_stdlib")
    @patch.object(GoInstallable.__bases__[0], "stage")
    def test_stage_skips_stdlib_when_disabled(
        self,
        mock_super_stage: MagicMock,
        mock_build_stdlib: MagicMock,
        mock_context: MagicMock,
        basic_config: dict,
        tmp_path: Path,
    ):
        """Test that stage() skips stdlib building when disabled in config."""
        basic_config["build_stdlib"] = False

        staging_mock = MagicMock()
        staging_mock.path = tmp_path / "staging"

        installable = GoInstallable(mock_context, basic_config)
        installable.stage(staging_mock)

        mock_super_stage.assert_called_once_with(staging_mock)
        mock_build_stdlib.assert_not_called()

    @patch("lib.installable.go.build_go_stdlib")
    @patch.object(GoInstallable.__bases__[0], "stage")
    def test_stage_calls_stdlib_in_dry_run(
        self,
        mock_super_stage: MagicMock,
        mock_build_stdlib: MagicMock,
        mock_context: MagicMock,
        basic_config: dict,
        tmp_path: Path,
    ):
        """Test that stage() calls build_go_stdlib with dry_run=True in dry-run mode."""
        mock_context.dry_run = True

        # Setup
        staging_dir = tmp_path / "staging"
        staging_dir.mkdir()
        go_install_dir = staging_dir / "golang-1.24.2"
        go_install_dir.mkdir()
        (go_install_dir / "go").mkdir()

        staging_mock = MagicMock()
        staging_mock.path = staging_dir

        mock_build_stdlib.return_value = True

        installable = GoInstallable(mock_context, basic_config)
        installable.stage(staging_mock)

        mock_super_stage.assert_called_once_with(staging_mock)
        mock_build_stdlib.assert_called_once()

        # Verify dry_run=True was passed
        call_kwargs = mock_build_stdlib.call_args[1]
        assert call_kwargs["dry_run"] is True

    @patch("lib.installable.go.build_go_stdlib")
    @patch.object(GoInstallable.__bases__[0], "stage")
    def test_stage_handles_build_failure_gracefully(
        self,
        mock_super_stage: MagicMock,
        mock_build_stdlib: MagicMock,
        mock_context: MagicMock,
        basic_config: dict,
        tmp_path: Path,
    ):
        """Test that stage() continues even if stdlib build fails."""
        # Setup
        staging_dir = tmp_path / "staging"
        staging_dir.mkdir()
        go_install_dir = staging_dir / "golang-1.24.2"
        go_install_dir.mkdir()
        (go_install_dir / "go").mkdir()

        staging_mock = MagicMock()
        staging_mock.path = staging_dir

        # Build returns False (failure)
        mock_build_stdlib.return_value = False

        installable = GoInstallable(mock_context, basic_config)

        # Should not raise, just log warning
        installable.stage(staging_mock)

        mock_super_stage.assert_called_once()
        mock_build_stdlib.assert_called_once()

    @patch("lib.installable.go.build_go_stdlib")
    @patch.object(GoInstallable.__bases__[0], "stage")
    def test_stage_handles_exception_gracefully(
        self,
        mock_super_stage: MagicMock,
        mock_build_stdlib: MagicMock,
        mock_context: MagicMock,
        basic_config: dict,
        tmp_path: Path,
    ):
        """Test that stage() continues even if stdlib build raises exception."""
        # Setup
        staging_dir = tmp_path / "staging"
        staging_dir.mkdir()
        go_install_dir = staging_dir / "golang-1.24.2"
        go_install_dir.mkdir()
        (go_install_dir / "go").mkdir()

        staging_mock = MagicMock()
        staging_mock.path = staging_dir

        # Build raises exception
        mock_build_stdlib.side_effect = RuntimeError("Build failed")

        installable = GoInstallable(mock_context, basic_config)

        # Should not raise, just log error
        installable.stage(staging_mock)

        mock_super_stage.assert_called_once()
        mock_build_stdlib.assert_called_once()

    @patch.object(GoInstallable.__bases__[0], "stage")
    def test_stage_raises_if_go_dir_not_found(
        self,
        mock_super_stage: MagicMock,
        mock_context: MagicMock,
        basic_config: dict,
        tmp_path: Path,
    ):
        """Test that stage() raises error if Go installation directory not found."""
        staging_mock = MagicMock()
        staging_mock.path = tmp_path / "staging"
        staging_mock.path.mkdir()

        installable = GoInstallable(mock_context, basic_config)

        with pytest.raises(RuntimeError, match="Go installation directory not found"):
            installable.stage(staging_mock)

    @patch("lib.installable.go.build_go_stdlib")
    @patch.object(GoInstallable.__bases__[0], "stage")
    def test_stage_uses_custom_architectures(
        self,
        mock_super_stage: MagicMock,
        mock_build_stdlib: MagicMock,
        mock_context: MagicMock,
        basic_config: dict,
        tmp_path: Path,
    ):
        """Test that stage() uses custom architectures from config."""
        basic_config["build_stdlib_archs"] = ["linux/amd64", "linux/386"]

        staging_dir = tmp_path / "staging"
        staging_dir.mkdir()
        go_install_dir = staging_dir / "golang-1.24.2"
        go_install_dir.mkdir()
        (go_install_dir / "go").mkdir()

        staging_mock = MagicMock()
        staging_mock.path = staging_dir

        mock_build_stdlib.return_value = True

        installable = GoInstallable(mock_context, basic_config)
        installable.stage(staging_mock)

        call_kwargs = mock_build_stdlib.call_args[1]
        assert call_kwargs["architectures"] == ["linux/amd64", "linux/386"]

    def test_repr(self, mock_context: MagicMock, basic_config: dict):
        """Test string representation of GoInstallable."""
        installable = GoInstallable(mock_context, basic_config)

        repr_str = repr(installable)

        assert "GoInstallable" in repr_str
        assert "golang-1.24.2" in repr_str
