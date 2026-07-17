"""Tests for go_module installable."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from lib.installable.go_module import GoModuleInstallable
from lib.installation_context import InstallationContext


@pytest.fixture
def mock_context(tmp_path: Path):
    """Create a mock installation context."""
    context = MagicMock(spec=InstallationContext)
    context.destination = tmp_path / "destination"
    context.destination.mkdir(parents=True, exist_ok=True)
    context.dry_run = False
    return context


@pytest.fixture
def basic_config():
    """Create basic Go module configuration."""
    return {
        "name": "v1.6.0",
        "type": "gomod",
        "module": "github.com/google/uuid",
        "build_type": "gomod",
        "context": ["libraries", "go", "uuid"],
    }


class TestGoModuleInstallableInit:
    """Tests for GoModuleInstallable initialization."""

    def test_init_with_module(self, mock_context, basic_config):
        """Test initialization with module config."""
        installable = GoModuleInstallable(mock_context, basic_config)

        assert installable.module_path == "github.com/google/uuid"
        assert installable.target_name == "v1.6.0"

    def test_init_without_module(self, mock_context):
        """Test initialization without module config uses empty string."""
        config = {
            "name": "v1.0.0",
            "type": "gomod",
            "context": ["libraries", "go", "test"],
        }
        installable = GoModuleInstallable(mock_context, config)

        assert not installable.module_path


class TestGoModuleInstallableIsInstalled:
    """Tests for is_installed method."""

    def test_is_installed_always_true(self, mock_context, basic_config):
        """Test that is_installed always returns True."""
        installable = GoModuleInstallable(mock_context, basic_config)

        # Should always be True since Conan handles installation
        assert installable.is_installed() is True


class TestGoModuleInstallableSquashable:
    """Tests for is_squashable property."""

    def test_is_not_squashable(self, mock_context, basic_config):
        """Test that Go modules are not squashable."""
        installable = GoModuleInstallable(mock_context, basic_config)

        assert installable.is_squashable is False


class TestGoModuleInstallableRepr:
    """Tests for __repr__ method."""

    def test_repr(self, mock_context, basic_config):
        """Test string representation."""
        installable = GoModuleInstallable(mock_context, basic_config)

        repr_str = repr(installable)
        assert "GoModuleInstallable" in repr_str
        assert "v1.6.0" in repr_str
        assert "github.com/google/uuid" in repr_str

    def test_repr_without_module(self, mock_context):
        """Test string representation without module."""
        config = {
            "name": "v1.0.0",
            "type": "gomod",
            "context": ["libraries", "go", "test"],
        }
        installable = GoModuleInstallable(mock_context, config)

        repr_str = repr(installable)
        assert "GoModuleInstallable" in repr_str
        assert "v1.0.0" in repr_str
