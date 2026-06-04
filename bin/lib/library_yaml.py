from __future__ import annotations

import os
from collections import defaultdict
from pathlib import Path

import yaml

from lib.amazon_properties import get_properties_compilers_and_libraries, get_specific_library_version_details
from lib.config_expand import is_value_type
from lib.config_safe_loader import ConfigSafeLoader
from lib.installation_context import FetchFailure
from lib.library_platform import LibraryPlatform
from lib.library_props import (
    generate_library_property_key,
    generate_version_property_key,
    should_skip_library_for_windows,
    version_to_id,
)
from lib.rust_crates import TopRustCrates


def collect_library_leaves(node) -> dict[str, list[dict]]:
    """Walk a libraries.yaml subtree, returning a flat libid -> [libdef, ...] mapping.

    A dict that carries a ``targets`` key is treated as a library leaf; any other
    dict is treated as a grouping node (e.g. ``nightly:``, ``beman:``) and recursed
    into. Each leaf's libdef is merged with the scalar/list properties inherited
    from its grouping ancestors, mirroring the inheritance the install pipeline
    performs in ``installation._targets_from``. The same libid can occur in
    multiple groupings, so values are lists.
    """

    leaves: dict[str, list[dict]] = defaultdict(list)

    def walk(d, inherited):
        if not isinstance(d, dict):
            return
        # Accumulate this node's own scalar/list props onto the inherited config,
        # so children see (and override) parent settings.
        local = dict(inherited)
        for key, value in d.items():
            if key != "targets" and is_value_type(value):
                local[key] = value
        # Two-pass walk: record leaves at the current level before descending into
        # grouping siblings. This matters for libids that appear in multiple places
        # (e.g. nlohmann_json directly under c++ and again under c++.nightly): the
        # outer-level libdef is recorded first, preserving the version order pristine
        # main produced for the generated Windows properties.
        for key, value in d.items():
            if not isinstance(value, dict) or "targets" not in value:
                continue
            merged = dict(local)
            for k, v in value.items():
                if is_value_type(v):
                    merged[k] = v
            merged["targets"] = value["targets"]
            leaves[key].append(merged)
        for value in d.values():
            if not isinstance(value, dict) or "targets" in value:
                continue
            walk(value, local)

    walk(node, {})
    return leaves


class LibraryYaml:
    def __init__(self, yaml_dir):
        self.yaml_dir = yaml_dir
        self.yaml_path = Path(os.path.join(self.yaml_dir, "libraries.yaml"))
        self.load()

    def load(self):
        with self.yaml_path.open(encoding="utf-8", mode="r") as yaml_file:
            self.yaml_doc = yaml.load(yaml_file, Loader=ConfigSafeLoader)

    def save(self):
        with self.yaml_path.open(encoding="utf-8", mode="w") as yaml_file:
            yaml.dump(self.yaml_doc, yaml_file)

    def reformat(self):
        self.save()

    def add_rust_crate(self, libid, libversion):
        if "rust" not in self.yaml_doc["libraries"]:
            self.yaml_doc["libraries"]["rust"] = dict()

        libraries_for_language = self.yaml_doc["libraries"]["rust"]
        if libid in libraries_for_language:
            if libversion not in libraries_for_language[libid]["targets"]:
                libraries_for_language[libid]["targets"].append(libversion)
        else:
            libraries_for_language[libid] = dict(type="cratesio", build_type="cargo", targets=[libversion])

    def get_ce_properties_for_rust_libraries(self) -> str:
        properties_txt = ""

        libraries_for_language = self.yaml_doc["libraries"]["rust"]
        for libid in libraries_for_language:
            all_libver_ids: list[str] = []

            for libver in libraries_for_language[libid]["targets"]:
                all_libver_ids.append(version_to_id(libver))

            name_key = generate_library_property_key(libid, "name")
            url_key = generate_library_property_key(libid, "url")
            versions_key = generate_library_property_key(libid, "versions")

            libverprops = f"{name_key}={libid}\n"
            libverprops += f"{url_key}=https://crates.io/crates/{libid}\n"
            libverprops += f"{versions_key}="
            libverprops += ":".join(all_libver_ids) + "\n"

            for libver in libraries_for_language[libid]["targets"]:
                libverid = version_to_id(libver)
                version_key = generate_version_property_key(libid, libverid, "version")
                path_key = generate_version_property_key(libid, libverid, "path")
                underscore_lib = libid.replace("-", "_")
                libverprops += f"{version_key}={libver}\n"
                libverprops += f"{path_key}=lib{underscore_lib}.rlib\n"

            properties_txt += libverprops + "\n"

        return properties_txt

    def add_top_rust_crates(self):
        cratelisting = TopRustCrates()
        crates = cratelisting.list(100)
        for crate in crates:
            self.add_rust_crate(crate["libid"], crate["libversion"])

    def _find_version_in_props(self, version_name: str, lib_props: dict | None) -> tuple[str, str] | None:
        """Find matching version in a properties lib dict for a YAML target name.

        Returns (ver_id, ver_name) if matched, or None.
        Checks version, lookupversion, and tries with/without 'v' prefix.
        Also tries matching version_to_id against existing ver_ids.
        """
        if not lib_props or "versionprops" not in lib_props:
            return None

        candidates = [version_name]
        if version_name.startswith("v"):
            candidates.append(version_name[1:])
        else:
            candidates.append("v" + version_name)

        for candidate in candidates:
            for ver_id, ver_props in lib_props["versionprops"].items():
                if ver_props.get("version") == candidate or ver_props.get("lookupversion") == candidate:
                    return (ver_id, str(ver_props.get("version", candidate)))

        stripped = version_to_id(version_name)
        for ver_id, ver_props in lib_props["versionprops"].items():
            if ver_id == stripped or ver_id == "v" + stripped:
                return (ver_id, str(ver_props.get("version", version_name)))

        return None

    def _resolve_version(self, version_name: str, *lib_props_list: dict | None) -> tuple[str, str] | None:
        """Find matching version, checking multiple property sources in priority order."""
        for lib_props in lib_props_list:
            match = self._find_version_in_props(version_name, lib_props)
            if match:
                return match
        return None

    def get_libverid(self, libver, linux_lib=None, existing_lib=None) -> str:
        if isinstance(libver, dict) and "name" in libver:
            version_name = libver["name"]
        else:
            version_name = libver
        match = self._resolve_version(version_name, existing_lib, linux_lib)
        if match:
            return match[0]
        return version_to_id(version_name)

    def get_libvername(self, libver, linux_lib=None, existing_lib=None) -> str:
        """Get version name, preferring existing version string when a match is found."""
        if isinstance(libver, dict) and "name" in libver:
            version_name = libver["name"]
        else:
            version_name = libver
        match = self._resolve_version(version_name, existing_lib, linux_lib)
        if match:
            return match[1]
        return version_name

    def get_possible_lookupname(self, linux_libraries, libid) -> str:
        for libkey in linux_libraries:
            lib = linux_libraries[libkey]
            if "lookupname" in lib:
                if libid == lib["lookupname"]:
                    return lib["id"]

            if "versionprops" in lib:
                for libverid in lib["versionprops"]:
                    libver = lib["versionprops"][libverid]
                    if "lookupname" in libver:
                        if libid == libver["lookupname"]:
                            return lib["id"]

        return libid

    def get_link_props(self, linux_lib_version, prefix) -> str:
        libverprops = ""
        if linux_lib_version:
            if "staticliblink" in linux_lib_version and linux_lib_version["staticliblink"]:
                linklist = ":".join(linux_lib_version["staticliblink"])
                libverprops += f"{prefix}.staticliblink={linklist}\n"
            if "liblink" in linux_lib_version and linux_lib_version["liblink"]:
                if prefix.startswith("libs.qt"):
                    # special case for qt, we need to add a 'd' to the end of the liblink on windows
                    linklist = ":".join(map(lambda link: link + "d", linux_lib_version["liblink"]))
                else:
                    linklist = ":".join(linux_lib_version["liblink"])
                libverprops += f"{prefix}.liblink={linklist}\n"
            if "dependencies" in linux_lib_version and linux_lib_version["dependencies"]:
                linklist = ":".join(linux_lib_version["dependencies"])
                libverprops += f"{prefix}.dependencies={linklist}\n"

        return libverprops

    def get_ce_properties_for_cpp_windows_libraries(self, logger) -> str:
        properties_txt = ""

        [_, linux_libraries] = get_properties_compilers_and_libraries("c++", logger, LibraryPlatform.Linux, False)

        try:
            [_, windows_libraries] = get_properties_compilers_and_libraries(
                "c++", logger, LibraryPlatform.Windows, False
            )
        except (FetchFailure, RuntimeError):
            logger.debug("Could not load existing Windows properties, proceeding without")
            windows_libraries = {}

        # Walk the c++ tree recursively. Any dict carrying a `targets` list is a leaf
        # (a library); every other dict is a grouping node (e.g. `nightly:` or `beman:`).
        # The same libid can appear in multiple groupings, so we keep all libdefs per id.
        libleaves: dict[str, list[dict]] = collect_library_leaves(self.yaml_doc["libraries"]["c++"])

        # id's in the yaml file are more unique than the ones in the linux (amazon) properties file (example boost & boost_bin)
        #  so we need to map them to the linux properties file using the .lookupname used in the linux properties file.
        # Track yaml libids per linux lookupname in insertion order (using dict-as-ordered-set)
        # so the resulting version order is deterministic.
        reorganised_libs: dict[str, dict[str, None]] = dict()
        for libid, libdefs in libleaves.items():
            if all(should_skip_library_for_windows(libid, libdef) for libdef in libdefs):
                continue

            linux_libid = libid
            lookupname = libid
            if linux_libid not in linux_libraries:
                if linux_libid == "catch2v2":
                    # hardcoded, we renamed this manually in the yaml file to distinguish catch2 versions that were
                    # header-only from the ones that are built
                    lookupname = "catch2"
                else:
                    lookupname = self.get_possible_lookupname(linux_libraries, linux_libid)

            # Only emit libs we already know about on either platform. Recursing into
            # nested groupings can surface keys (e.g. flavor names like microsoft/ngcpp
            # under c++.proxy) that aren't standalone libraries -- skip those rather
            # than producing stub entries that would pollute the merged Windows config.
            if lookupname not in linux_libraries and lookupname not in windows_libraries:
                continue

            if lookupname not in reorganised_libs:
                reorganised_libs[lookupname] = dict()

            logger.debug(f"Mapping {linux_libid} to {lookupname}")
            reorganised_libs[lookupname][linux_libid] = None

        for linux_libid, yamllibids in reorganised_libs.items():
            linux_lib = linux_libraries[linux_libid]
            existing_lib = windows_libraries.get(linux_libid)

            libname = linux_libid
            if "name" in linux_lib:
                libname = linux_lib["name"]

            name_property_key = generate_library_property_key(linux_libid, "name")
            libverprops = f"{name_property_key}={libname}\n"
            if "url" in linux_lib:
                url_property_key = generate_library_property_key(linux_libid, "url")
                libverprops += f"{url_property_key}={linux_lib['url']}\n"
            if "description" in linux_lib:
                description_property_key = generate_library_property_key(linux_libid, "description")
                libverprops += f"{description_property_key}={linux_lib['description']}\n"
            packagedheaders_property_key = generate_library_property_key(linux_libid, "packagedheaders")
            libverprops += f"{packagedheaders_property_key}=true\n"

            all_libver_ids: list[str] = []
            for yamllibid in yamllibids:
                for libdef in libleaves.get(yamllibid, []):
                    for libver in libdef["targets"]:
                        all_libver_ids.append(self.get_libverid(libver, linux_lib, existing_lib))

            versions_property_key = generate_library_property_key(linux_libid, "versions")
            libverprops += f"{versions_property_key}="
            libverprops += ":".join(all_libver_ids) + "\n"

            prefix = generate_library_property_key(linux_libid, "")
            prefix = prefix.rstrip(".")
            libverprops += self.get_link_props(linux_lib, prefix)

            for yamllibid in yamllibids:
                for libdef in libleaves.get(yamllibid, []):
                    for libver in libdef["targets"]:
                        libverid = self.get_libverid(libver, linux_lib, existing_lib)
                        libvername = self.get_libvername(libver, linux_lib, existing_lib)
                        version_property_key = generate_version_property_key(linux_libid, libverid, "version")
                        libverprops += f"{version_property_key}={libvername}\n"
                        linux_lib_version = get_specific_library_version_details(linux_libraries, linux_libid, libverid)
                        if not linux_lib_version:
                            linux_lib_version = get_specific_library_version_details(
                                linux_libraries, linux_libid, libvername
                            )

                        prefix = generate_version_property_key(linux_libid, libverid, "")
                        prefix = prefix.rstrip(".")
                        libverprops += self.get_link_props(linux_lib_version, prefix)

            properties_txt += libverprops + "\n"

        return properties_txt

    @classmethod
    def load_library_yaml_section(cls, language):
        """Load libraries.yaml and return the specified language section."""
        yaml_dir = Path(__file__).parent.parent / "yaml"
        library_yaml = cls(str(yaml_dir))

        # Ensure language section exists
        if language not in library_yaml.yaml_doc["libraries"]:
            library_yaml.yaml_doc["libraries"][language] = {}

        return library_yaml, library_yaml.yaml_doc["libraries"][language]
