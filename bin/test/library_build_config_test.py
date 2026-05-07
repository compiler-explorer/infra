from __future__ import annotations

import pytest
from lib.library_build_config import LibraryBuildConfig


def _config(**overrides):
    base = {"build_type": "none"}
    base.update(overrides)
    return base


class TestLibTypeValidation:
    def test_default_lib_type_is_headeronly(self):
        cfg = LibraryBuildConfig(_config())
        assert cfg.lib_type == "headeronly"

    def test_invalid_lib_type_rejected(self):
        with pytest.raises(RuntimeError, match="not a valid lib_type"):
            LibraryBuildConfig(_config(lib_type="bogus"))

    def test_headeronly_forbids_staticliblink(self):
        with pytest.raises(RuntimeError, match="should not have staticliblink"):
            LibraryBuildConfig(_config(lib_type="headeronly", staticliblink=["foo"]))

    def test_headeronly_forbids_sharedliblink(self):
        with pytest.raises(RuntimeError, match="should not have staticliblink or sharedliblink"):
            LibraryBuildConfig(_config(lib_type="headeronly", sharedliblink=["foo"]))


class TestCmakeBuiltHeaderonly:
    def test_minimum_valid_config(self):
        cfg = LibraryBuildConfig(_config(lib_type="cmake_built_headeronly", build_type="cmake", package_install=True))
        assert cfg.lib_type == "cmake_built_headeronly"
        assert cfg.package_install is True

    def test_requires_cmake_build_type(self):
        with pytest.raises(RuntimeError, match="requires build_type: cmake"):
            LibraryBuildConfig(_config(lib_type="cmake_built_headeronly", build_type="none", package_install=True))

    def test_requires_package_install(self):
        with pytest.raises(RuntimeError, match="requires package_install: true"):
            LibraryBuildConfig(_config(lib_type="cmake_built_headeronly", build_type="cmake"))

    def test_forbids_staticliblink(self):
        with pytest.raises(RuntimeError, match="should not have staticliblink"):
            LibraryBuildConfig(
                _config(
                    lib_type="cmake_built_headeronly",
                    build_type="cmake",
                    package_install=True,
                    staticliblink=["foo"],
                )
            )

    def test_forbids_sharedliblink(self):
        with pytest.raises(RuntimeError, match="should not have staticliblink or sharedliblink"):
            LibraryBuildConfig(
                _config(
                    lib_type="cmake_built_headeronly",
                    build_type="cmake",
                    package_install=True,
                    sharedliblink=["foo"],
                )
            )


class TestCsharedValidation:
    def test_cshared_requires_use_compiler(self):
        with pytest.raises(RuntimeError, match="required to supply a .cross.compiler"):
            LibraryBuildConfig(_config(lib_type="cshared"))
