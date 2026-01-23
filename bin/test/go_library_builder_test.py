"""Tests for go_library_builder module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from lib.go_library_builder import BuildStatus, GoLibraryBuilder, clear_properties_cache
from lib.library_build_config import LibraryBuildConfig


@pytest.fixture(autouse=True)
def clear_props_cache():
    """Clear the properties cache before each test."""
    clear_properties_cache()
    yield
    clear_properties_cache()


def create_go_test_build_config():
    """Create properly configured LibraryBuildConfig for Go tests."""
    config = MagicMock(spec=LibraryBuildConfig)
    config.build_type = "gomod"
    config.lib_type = "static"
    config.module = "github.com/google/uuid"
    config.description = "Test Go library"
    config.url = "https://github.com/google/uuid"
    config.skip_compilers = []
    config.config_get = lambda key, default="": {
        "module": "github.com/google/uuid",
        "build_type": "gomod",
    }.get(key, default)
    return config


class TestGoLibraryBuilderInit:
    """Tests for GoLibraryBuilder initialization."""

    @patch("lib.go_library_builder.get_properties_compilers_and_libraries")
    def test_init_basic(self, mock_get_props):
        """Test basic initialization."""
        mock_get_props.return_value = ({"gl1238": {"exe": "/opt/go/bin/go"}}, {})
        logger = MagicMock()
        install_context = MagicMock()
        buildconfig = create_go_test_build_config()

        builder = GoLibraryBuilder(
            logger=logger,
            language="go",
            libname="uuid",
            target_name="v1.6.0",
            install_context=install_context,
            buildconfig=buildconfig,
        )

        assert builder.libname == "uuid"
        assert builder.target_name == "v1.6.0"
        assert builder.module_path == "github.com/google/uuid"
        assert builder.language == "go"

    @patch("lib.go_library_builder.get_properties_compilers_and_libraries")
    def test_init_missing_module_raises(self, mock_get_props):
        """Test that missing module config raises error."""
        mock_get_props.return_value = ({}, {})
        logger = MagicMock()
        install_context = MagicMock()
        buildconfig = MagicMock(spec=LibraryBuildConfig)
        buildconfig.config_get = lambda key, default="": default  # Returns empty for module

        with pytest.raises(RuntimeError, match="Missing 'module' config"):
            GoLibraryBuilder(
                logger=logger,
                language="go",
                libname="test",
                target_name="v1.0.0",
                install_context=install_context,
                buildconfig=buildconfig,
            )


class TestGoLibraryBuilderHelpers:
    """Tests for helper methods."""

    @patch("lib.go_library_builder.get_properties_compilers_and_libraries")
    def test_get_go_binary(self, mock_get_props):
        """Test getting Go binary path."""
        mock_get_props.return_value = (
            {"gl1238": {"exe": "/opt/compiler-explorer/golang-1.23.8/go/bin/go"}},
            {},
        )
        logger = MagicMock()
        install_context = MagicMock()
        buildconfig = create_go_test_build_config()

        builder = GoLibraryBuilder(
            logger=logger,
            language="go",
            libname="uuid",
            target_name="v1.6.0",
            install_context=install_context,
            buildconfig=buildconfig,
        )

        binary = builder._get_go_binary("gl1238")
        assert binary == Path("/opt/compiler-explorer/golang-1.23.8/go/bin/go")

    @patch("lib.go_library_builder.get_properties_compilers_and_libraries")
    def test_get_goroot(self, mock_get_props):
        """Test getting GOROOT path."""
        mock_get_props.return_value = (
            {"gl1238": {"exe": "/opt/compiler-explorer/golang-1.23.8/go/bin/go"}},
            {},
        )
        logger = MagicMock()
        install_context = MagicMock()
        buildconfig = create_go_test_build_config()

        builder = GoLibraryBuilder(
            logger=logger,
            language="go",
            libname="uuid",
            target_name="v1.6.0",
            install_context=install_context,
            buildconfig=buildconfig,
        )

        goroot = builder._get_goroot("gl1238")
        assert goroot == Path("/opt/compiler-explorer/golang-1.23.8/go")

    @patch("lib.go_library_builder.get_properties_compilers_and_libraries")
    def test_makebuildhash(self, mock_get_props):
        """Test build hash generation."""
        mock_get_props.return_value = ({"gl1238": {"exe": "/opt/go/bin/go"}}, {})
        logger = MagicMock()
        install_context = MagicMock()
        buildconfig = create_go_test_build_config()

        builder = GoLibraryBuilder(
            logger=logger,
            language="go",
            libname="uuid",
            target_name="v1.6.0",
            install_context=install_context,
            buildconfig=buildconfig,
        )

        hash1 = builder.makebuildhash("gl1238", "Linux", "Debug", "x86_64")
        hash2 = builder.makebuildhash("gl1238", "Linux", "Debug", "x86_64")
        hash3 = builder.makebuildhash("gl1239", "Linux", "Debug", "x86_64")

        # Same inputs should give same hash
        assert hash1 == hash2
        # Different compiler should give different hash
        assert hash1 != hash3
        # Hash should start with compiler name
        assert hash1.startswith("gl1238_")


class TestGoLibraryBuilderConanHelpers:
    """Tests for Conan-related helper methods."""

    @patch("lib.go_library_builder.get_properties_compilers_and_libraries")
    def test_set_conan_build_parameters(self, mock_get_props):
        """Test setting Conan build parameters."""
        mock_get_props.return_value = ({"gl1238": {"exe": "/opt/go/bin/go"}}, {})
        logger = MagicMock()
        install_context = MagicMock()
        buildconfig = create_go_test_build_config()

        builder = GoLibraryBuilder(
            logger=logger,
            language="go",
            libname="uuid",
            target_name="v1.6.0",
            install_context=install_context,
            buildconfig=buildconfig,
        )

        builder.set_current_conan_build_parameters("Linux", "Debug", "gl1238", "x86_64")

        assert builder.current_buildparameters_obj["os"] == "Linux"
        assert builder.current_buildparameters_obj["buildtype"] == "Debug"
        assert builder.current_buildparameters_obj["compiler"] == "gc"
        assert builder.current_buildparameters_obj["compiler_version"] == "gl1238"
        assert builder.current_buildparameters_obj["library"] == "go_uuid"
        assert builder.current_buildparameters_obj["library_version"] == "v1.6.0"

    @patch("lib.go_library_builder.get_properties_compilers_and_libraries")
    def test_writeconanfile(self, mock_get_props, tmp_path):
        """Test writing Conan package file."""
        mock_get_props.return_value = ({"gl1238": {"exe": "/opt/go/bin/go"}}, {})
        logger = MagicMock()
        install_context = MagicMock()
        buildconfig = create_go_test_build_config()

        builder = GoLibraryBuilder(
            logger=logger,
            language="go",
            libname="uuid",
            target_name="v1.6.0",
            install_context=install_context,
            buildconfig=buildconfig,
        )

        builder.writeconanfile(tmp_path)

        conanfile = tmp_path / "conanfile.py"
        assert conanfile.exists()
        content = conanfile.read_text()
        assert "class go_uuidConan(ConanFile):" in content
        assert 'name = "go_uuid"' in content
        assert 'version = "v1.6.0"' in content


class TestGoLibraryBuilderBuildStatus:
    """Tests for BuildStatus enum."""

    def test_build_status_values(self):
        """Test BuildStatus enum values."""
        assert BuildStatus.Ok.value == 0
        assert BuildStatus.Failed.value == 1
        assert BuildStatus.Skipped.value == 2
        assert BuildStatus.TimedOut.value == 3
