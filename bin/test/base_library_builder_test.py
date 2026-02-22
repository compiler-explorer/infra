from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from lib.base_library_builder import CONANINFOHASH_RE, BaseLibraryBuilder
from lib.library_build_config import LibraryBuildConfig


@pytest.fixture
def test_builder():
    """Create a test builder instance."""
    logger = MagicMock()
    install_context = MagicMock()
    install_context.dry_run = False
    buildconfig = LibraryBuildConfig({
        "lib_type": "static",
        "package_dir": "libs",
        "source_archive": "",
    })

    # Create a concrete test class since BaseLibraryBuilder is abstract
    class TestBuilder(BaseLibraryBuilder):
        def completeBuildConfig(self):
            pass

        def makebuild(self, buildfor):
            pass

        def makebuildfor(self, *args):
            pass

        def writeconanfile(self, buildfolder):
            pass

    return TestBuilder(
        logger=logger,
        language="c++",
        libname="testlib",
        target_name="1.0",
        sourcefolder="/tmp/test",
        install_context=install_context,
        buildconfig=buildconfig,
    )


def test_setCurrentConanBuildParameters_format(test_builder):
    """Test that conan parameters are built in the correct format."""
    # Call the method with typical parameters
    test_builder.setCurrentConanBuildParameters(
        buildos="Linux",
        buildtype="Debug",
        compilerTypeOrGcc="gcc",
        compiler="11.1.0",
        libcxx="libstdc++",
        arch="x86_64",
        stdver="c++17",
        extraflags="",
    )

    # Expected format: alternating "-s" and "key=value" as separate list items
    expected = [
        "-s",
        "os=Linux",
        "-s",
        "build_type=Debug",
        "-s",
        "compiler=gcc",
        "-s",
        "compiler.version=11.1.0",
        "-s",
        "compiler.libcxx=libstdc++",
        "-s",
        "arch=x86_64",
        "-s",
        "stdver=c++17",
        "-s",
        "flagcollection=",
    ]

    assert test_builder.current_buildparameters == expected


def test_setCurrentConanBuildParameters_with_defaults(test_builder):
    """Test parameter building with None/empty values that trigger defaults."""
    test_builder.setCurrentConanBuildParameters(
        buildos="Linux",
        buildtype="Release",
        compilerTypeOrGcc=None,  # Should default to "gcc"
        compiler="10.2.0",
        libcxx=None,  # Should default to "libstdc++"
        arch="x86",
        stdver="",
        extraflags="",
    )

    expected = [
        "-s",
        "os=Linux",
        "-s",
        "build_type=Release",
        "-s",
        "compiler=gcc",  # defaulted
        "-s",
        "compiler.version=10.2.0",
        "-s",
        "compiler.libcxx=libstdc++",  # defaulted
        "-s",
        "arch=x86",
        "-s",
        "stdver=",
        "-s",
        "flagcollection=",
    ]

    assert test_builder.current_buildparameters == expected


def test_setCurrentConanBuildParameters_includes_flagcollection(test_builder):
    """Test that flagcollection is included in conan parameters list."""
    test_builder.setCurrentConanBuildParameters(
        buildos="Linux",
        buildtype="Debug",
        compilerTypeOrGcc="clang",
        compiler="14.0.0",
        libcxx="libc++",
        arch="x86_64",
        stdver="c++20",
        extraflags="-O3",
    )

    # Verify flagcollection is in the object
    assert test_builder.current_buildparameters_obj["flagcollection"] == "-O3"

    # Verify it IS in the parameter list (original behavior)
    param_strings = " ".join(test_builder.current_buildparameters)
    assert "flagcollection=-O3" in param_strings


def test_conan_parameter_format_for_command_line(test_builder):
    """Test that parameters can be used directly with conan command."""
    test_builder.setCurrentConanBuildParameters("Linux", "Debug", "gcc", "11.1.0", "libstdc++", "x86_64", "c++17", "")

    # Simulate building a conan command
    conan_cmd = ["conan", "info", "."] + test_builder.current_buildparameters

    # Verify the command would be correctly formatted
    expected_cmd = [
        "conan",
        "info",
        ".",
        "-s",
        "os=Linux",
        "-s",
        "build_type=Debug",
        "-s",
        "compiler=gcc",
        "-s",
        "compiler.version=11.1.0",
        "-s",
        "compiler.libcxx=libstdc++",
        "-s",
        "arch=x86_64",
        "-s",
        "stdver=c++17",
        "-s",
        "flagcollection=",
    ]

    assert conan_cmd == expected_cmd


def test_conan_hash_regex_with_real_output():
    """Test that the regex pattern matches actual conan info output."""
    # Test real conan info output format (based on what's expected from conan)
    conan_output = """
[project/1.0@celibs/trunk]
    ID: 5ab84d28a1f62d3983d85f5b69d0e4e45741e7e9
    BuildID: None
    Context: host
    """

    match = CONANINFOHASH_RE.search(conan_output)
    assert match is not None
    assert match.group(1) == "5ab84d28a1f62d3983d85f5b69d0e4e45741e7e9"


@pytest.mark.parametrize(
    "text,expected_hash",
    [
        # Standard conan output formats we expect
        ("    ID: abc123def456", "abc123def456"),
        ("\tID: 789abc", "789abc"),
        ("    ID: 5ab84d28a1f62d3983d85f5b69d0e4e45741e7e9", "5ab84d28a1f62d3983d85f5b69d0e4e45741e7e9"),
        # Edge case: empty hash (allowed by \w*)
        ("    ID: ", ""),
    ],
)
def test_conan_hash_regex_valid_patterns(text, expected_hash):
    """Test regex matches valid ID patterns from conan output."""
    match = CONANINFOHASH_RE.search(text)
    assert match is not None
    assert match.group(1) == expected_hash


@pytest.mark.parametrize(
    "text",
    [
        "ID: abc123",  # No whitespace before ID:
        "    ID:abc123",  # No whitespace after ID:
    ],
)
def test_conan_hash_regex_invalid_patterns(text):
    """Test regex correctly rejects invalid patterns."""
    match = CONANINFOHASH_RE.search(text)
    assert match is None
