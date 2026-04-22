from __future__ import annotations

from collections import defaultdict

from lib.library_yaml import LibraryYaml


def make_lib_props(versions: dict) -> dict:
    """Build a lib dict matching the structure from amazon_properties."""
    versionprops = {}
    for ver_id, props in versions.items():
        versionprops[ver_id] = defaultdict(lambda: [], props)
    return {"versionprops": versionprops}


class TestFindVersionInProps:
    def test_exact_version_match(self):
        lib = make_lib_props({"334": {"version": "3.3.4"}})
        yaml = LibraryYaml.__new__(LibraryYaml)
        assert yaml._find_version_in_props("3.3.4", lib) == ("334", "3.3.4")

    def test_lookupversion_match(self):
        lib = make_lib_props({"197": {"version": "19.7", "lookupversion": "v19.7"}})
        yaml = LibraryYaml.__new__(LibraryYaml)
        assert yaml._find_version_in_props("v19.7", lib) == ("197", "19.7")

    def test_v_prefix_added(self):
        lib = make_lib_props({"100": {"version": "v1.0"}})
        yaml = LibraryYaml.__new__(LibraryYaml)
        assert yaml._find_version_in_props("1.0", lib) == ("100", "v1.0")

    def test_v_prefix_stripped(self):
        lib = make_lib_props({"trunk": {"version": "trunk"}})
        yaml = LibraryYaml.__new__(LibraryYaml)
        assert yaml._find_version_in_props("vtrunk", lib) == ("trunk", "trunk")

    def test_version_to_id_with_v_prefix(self):
        lib = make_lib_props({"v2021100": {"version": "v2021100"}})
        yaml = LibraryYaml.__new__(LibraryYaml)
        assert yaml._find_version_in_props("2021.10.0", lib) == ("v2021100", "v2021100")

    def test_version_to_id_without_v_prefix(self):
        lib = make_lib_props({"v12": {"version": "12.0.0"}})
        yaml = LibraryYaml.__new__(LibraryYaml)
        assert yaml._find_version_in_props("12", lib) == ("v12", "12.0.0")

    def test_no_match(self):
        lib = make_lib_props({"trunk": {"version": "trunk"}})
        yaml = LibraryYaml.__new__(LibraryYaml)
        assert yaml._find_version_in_props("development", lib) is None

    def test_none_lib(self):
        yaml = LibraryYaml.__new__(LibraryYaml)
        assert yaml._find_version_in_props("1.0", None) is None

    def test_no_versionprops(self):
        yaml = LibraryYaml.__new__(LibraryYaml)
        assert yaml._find_version_in_props("1.0", {"name": "test"}) is None


class TestResolveVersion:
    def test_existing_wins_over_linux(self):
        """Existing Windows properties take priority over Linux."""
        linux_lib = make_lib_props({"197": {"version": "19.7", "lookupversion": "v19.7"}})
        existing_lib = make_lib_props({"v197": {"version": "v19.7"}})
        yaml = LibraryYaml.__new__(LibraryYaml)
        result = yaml._resolve_version("v19.7", existing_lib, linux_lib)
        assert result == ("v197", "v19.7")

    def test_falls_back_to_linux(self):
        """Falls back to Linux when no existing match."""
        linux_lib = make_lib_props({"197": {"version": "19.7", "lookupversion": "v19.7"}})
        yaml = LibraryYaml.__new__(LibraryYaml)
        result = yaml._resolve_version("v19.7", None, linux_lib)
        assert result == ("197", "19.7")

    def test_no_match_anywhere(self):
        linux_lib = make_lib_props({"trunk": {"version": "trunk"}})
        existing_lib = make_lib_props({"trunk": {"version": "trunk"}})
        yaml = LibraryYaml.__new__(LibraryYaml)
        assert yaml._resolve_version("development", existing_lib, linux_lib) is None


class TestGetLibverid:
    def test_existing_takes_priority(self):
        linux_lib = make_lib_props({"197": {"version": "19.7", "lookupversion": "v19.7"}})
        existing_lib = make_lib_props({"v197": {"version": "v19.7"}})
        yaml = LibraryYaml.__new__(LibraryYaml)
        assert yaml.get_libverid("v19.7", linux_lib, existing_lib) == "v197"

    def test_linux_fallback(self):
        linux_lib = make_lib_props({"110": {"version": "1.10.0", "lookupversion": "release-1.10.0"}})
        yaml = LibraryYaml.__new__(LibraryYaml)
        assert yaml.get_libverid("release-1.10.0", linux_lib) == "110"

    def test_without_any_props(self):
        yaml = LibraryYaml.__new__(LibraryYaml)
        assert yaml.get_libverid("1.2.3") == "123"

    def test_dict_libver(self):
        linux_lib = make_lib_props({"100": {"version": "v1.0"}})
        yaml = LibraryYaml.__new__(LibraryYaml)
        assert yaml.get_libverid({"name": "1.0"}, linux_lib) == "100"

    def test_fallback_to_version_to_id(self):
        linux_lib = make_lib_props({"trunk": {"version": "trunk"}})
        yaml = LibraryYaml.__new__(LibraryYaml)
        assert yaml.get_libverid("development", linux_lib) == "development"


class TestGetLibvername:
    def test_existing_version_preserved(self):
        """Existing Windows version string is preserved over Linux."""
        linux_lib = make_lib_props({"197": {"version": "19.7"}})
        existing_lib = make_lib_props({"v197": {"version": "v19.7"}})
        yaml = LibraryYaml.__new__(LibraryYaml)
        assert yaml.get_libvername("v19.7", linux_lib, existing_lib) == "v19.7"

    def test_linux_version_used_when_no_existing(self):
        linux_lib = make_lib_props({"100": {"version": "v1.0"}})
        yaml = LibraryYaml.__new__(LibraryYaml)
        assert yaml.get_libvername("1.0", linux_lib) == "v1.0"

    def test_yaml_name_when_no_match(self):
        linux_lib = make_lib_props({"trunk": {"version": "trunk"}})
        yaml = LibraryYaml.__new__(LibraryYaml)
        assert yaml.get_libvername("development", linux_lib) == "development"

    def test_yaml_name_when_no_props(self):
        yaml = LibraryYaml.__new__(LibraryYaml)
        assert yaml.get_libvername("1.0") == "1.0"

    def test_dict_libver(self):
        linux_lib = make_lib_props({"197": {"version": "19.7", "lookupversion": "v19.7"}})
        yaml = LibraryYaml.__new__(LibraryYaml)
        assert yaml.get_libvername({"name": "v19.7"}, linux_lib) == "19.7"
