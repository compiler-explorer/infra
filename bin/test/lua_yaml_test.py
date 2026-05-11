"""Regression test for Lua interpreter support (issue #2116)."""

from __future__ import annotations

from pathlib import Path

from lib.build_check import get_all_targets_from_yaml, get_targets_with_types

LUA_YAML = Path(__file__).parent.parent / "yaml" / "lua.yaml"
EXPECTED_LUA_VERSIONS = ("5.1.5", "5.2.4", "5.3.6", "5.4.7", "5.5.0")


def test_lua_yaml_exists():
    assert LUA_YAML.is_file(), f"{LUA_YAML} should exist to provide Lua interpreter installables"


def test_lua_yaml_contains_expected_versions():
    targets = get_all_targets_from_yaml(LUA_YAML)
    versions = {target for context, target in targets if context == ("compilers", "lua")}
    assert set(EXPECTED_LUA_VERSIONS).issubset(versions), (
        f"Expected Lua versions {EXPECTED_LUA_VERSIONS} under compilers/lua; got {sorted(versions)}"
    )


def test_lua_yaml_uses_s3tarballs_installer():
    targets_with_types = get_targets_with_types(LUA_YAML)
    for version in EXPECTED_LUA_VERSIONS:
        key = (("compilers", "lua"), version)
        assert targets_with_types.get(key) == "s3tarballs", (
            f"Lua {version} should be installed via s3tarballs; got {targets_with_types.get(key)}"
        )
