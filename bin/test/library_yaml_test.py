from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import yaml
from lib.config_safe_loader import ConfigSafeLoader
from lib.library_yaml import LibraryYaml, collect_library_leaves, insert_sorted


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


class TestCollectLibraryLeaves:
    def test_finds_top_level_leaves(self):
        leaves = collect_library_leaves({"foo": {"targets": ["1.0"]}, "bar": {"targets": ["2.0"]}})
        assert set(leaves.keys()) == {"foo", "bar"}
        assert leaves["foo"][0]["targets"] == ["1.0"]

    def test_grouping_node_recursed_into(self):
        leaves = collect_library_leaves({"group": {"foo": {"targets": ["1.0"]}}})
        assert "group" not in leaves
        assert leaves["foo"][0]["targets"] == ["1.0"]

    def test_inherits_scalar_props_from_grouping(self):
        leaves = collect_library_leaves({
            "group": {"build_type": "cmake", "type": "github", "foo": {"targets": ["1.0"]}}
        })
        libdef = leaves["foo"][0]
        assert libdef["build_type"] == "cmake"
        assert libdef["type"] == "github"

    def test_inherits_list_props_from_grouping(self):
        leaves = collect_library_leaves({"group": {"extra_cmake_arg": ["-DFOO=1"], "foo": {"targets": ["1.0"]}}})
        assert leaves["foo"][0]["extra_cmake_arg"] == ["-DFOO=1"]

    def test_leaf_overrides_inherited(self):
        leaves = collect_library_leaves({
            "group": {"build_type": "none", "foo": {"build_type": "cmake", "targets": ["1.0"]}}
        })
        assert leaves["foo"][0]["build_type"] == "cmake"

    def test_same_libid_in_multiple_groupings(self):
        leaves = collect_library_leaves({
            "foo": {"targets": ["1.0"]},
            "nightly": {"foo": {"targets": ["trunk"]}},
        })
        assert len(leaves["foo"]) == 2
        # Outer-level leaf is recorded before the one inside the nested grouping.
        assert leaves["foo"][0]["targets"] == ["1.0"]
        assert leaves["foo"][1]["targets"] == ["trunk"]

    def test_deeply_nested(self):
        leaves = collect_library_leaves({"outer": {"target_prefix": "v", "inner": {"foo": {"targets": ["1.0"]}}}})
        assert leaves["foo"][0]["target_prefix"] == "v"
        assert leaves["foo"][0]["targets"] == ["1.0"]

    def test_targets_key_makes_a_leaf_even_with_dict_children(self):
        # If a node has both `targets` and dict children, the node itself is treated
        # as a library leaf. Children are not recursed into.
        leaves = collect_library_leaves({"foo": {"targets": ["1.0"], "child": {"targets": ["2.0"]}}})
        assert "foo" in leaves
        assert "child" not in leaves


class TestRoundTrip:
    SAMPLE = """libraries:
  c++:
    # A comment that must survive a save.
    beta:
      repo: example/beta
      targets:
      - '1.10'
      - 2.0.0
      type: github
    alpha:
      type: github
      description: "Quoted, and keys deliberately unsorted"
      targets:
      - 1.0.0
"""

    def _library_yaml(self, tmp_path, text):
        (tmp_path / "libraries.yaml").write_text(text)
        return LibraryYaml(str(tmp_path))

    def test_unchanged_save_is_byte_identical(self, tmp_path):
        library_yaml = self._library_yaml(tmp_path, self.SAMPLE)
        library_yaml.save()
        assert (tmp_path / "libraries.yaml").read_text() == self.SAMPLE

    def test_adding_a_target_only_adds_that_line(self, tmp_path):
        library_yaml = self._library_yaml(tmp_path, self.SAMPLE)
        library_yaml.yaml_doc["libraries"]["c++"]["beta"]["targets"].append("3.0.0")
        library_yaml.save()
        assert (tmp_path / "libraries.yaml").read_text() == self.SAMPLE.replace(
            "      - 2.0.0\n", "      - 2.0.0\n      - 3.0.0\n"
        )

    def test_insert_sorted_places_new_library_alphabetically(self, tmp_path):
        library_yaml = self._library_yaml(tmp_path, "libraries:\n  c++:\n    apple: {}\n    cherry: {}\n")
        insert_sorted(library_yaml.yaml_doc["libraries"]["c++"], "banana", {"type": "github", "repo": "x/banana"})
        assert list(library_yaml.yaml_doc["libraries"]["c++"]) == ["apple", "banana", "cherry"]
        assert list(library_yaml.yaml_doc["libraries"]["c++"]["banana"]) == ["repo", "type"]

    def test_real_file_loads_the_same_data_as_the_install_loader(self):
        # The installer reads libraries.yaml with ConfigSafeLoader (YAML 1.1, no timestamps); the round-trip
        # loader is YAML 1.2. Values like `yes` or a bare date would load differently, so catch them here.
        yaml_dir = Path(__file__).parent.parent / "yaml"
        with (yaml_dir / "libraries.yaml").open(encoding="utf-8") as f:
            expected = yaml.load(f, Loader=ConfigSafeLoader)
        assert _plain(LibraryYaml(str(yaml_dir)).yaml_doc) == expected


def _plain(node):
    if isinstance(node, dict):
        return {str(k): _plain(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_plain(v) for v in node]
    if isinstance(node, bool) or node is None:
        return node
    for kind in (int, float):
        if isinstance(node, kind):
            return kind(node)
    return str(node)
