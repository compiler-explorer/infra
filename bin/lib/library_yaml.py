from __future__ import annotations

import os
from pathlib import Path

import yaml

from lib.amazon_properties import get_properties_compilers_and_libraries, get_specific_library_version_details
from lib.config_safe_loader import ConfigSafeLoader
from lib.library_platform import LibraryPlatform
from lib.library_props import (
    generate_library_property_key,
    generate_version_property_key,
    should_skip_library_for_windows,
    version_to_id,
)
from lib.rust_crates import TopRustCrates


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
        all_ids: list[str] = []
        properties_txt = ""

        libraries_for_language = self.yaml_doc["libraries"]["rust"]
        for libid in libraries_for_language:
            all_ids.append(libid)

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

        header_properties_txt = "libs=" + ":".join(all_ids) + "\n\n"

        return header_properties_txt + properties_txt

    def add_top_rust_crates(self):
        cratelisting = TopRustCrates()
        crates = cratelisting.list(100)
        for crate in crates:
            self.add_rust_crate(crate["libid"], crate["libversion"])

    def get_libverid(self, libver) -> str:
        if isinstance(libver, dict) and "name" in libver:
            version_name = libver["name"]
        else:
            version_name = libver
        return version_to_id(version_name)

    def get_libvername(self, libver) -> str:
        if isinstance(libver, dict) and "name" in libver:
            libverid = libver["name"]
        else:
            libverid = libver
        return libverid

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
        all_ids: list[str] = []
        properties_txt = ""

        [_, linux_libraries] = get_properties_compilers_and_libraries("c++", logger, LibraryPlatform.Linux, False)

        reorganised_libs: dict[str, set] = dict()

        # id's in the yaml file are more unique than the ones in the linux (amazon) properties file (example boost & boost_bin)
        #  so we need to map them to the linux properties file using the .lookupname used in the linux properties file
        libraries_for_language = self.yaml_doc["libraries"]["c++"]
        for libid in libraries_for_language:
            linux_libid = libid
            lookupname = libid
            if linux_libid not in linux_libraries:
                if linux_libid == "catch2v2":
                    # hardcoded, we renamed this manually in the yaml file to distinguish catch2 versions that were
                    # header-only from the ones that are built
                    lookupname = "catch2"
                else:
                    lookupname = self.get_possible_lookupname(linux_libraries, linux_libid)
            if should_skip_library_for_windows(lookupname, libraries_for_language[libid]):
                continue

            if lookupname not in reorganised_libs:
                reorganised_libs[lookupname] = set()

            logger.debug(f"Mapping {linux_libid} to {lookupname}")
            reorganised_libs[lookupname].add(linux_libid)

        nightly_libraries_for_language = self.yaml_doc["libraries"]["c++"]["nightly"]
        for libid in nightly_libraries_for_language:
            linux_libid = libid
            lookupname = libid
            if linux_libid not in linux_libraries:
                lookupname = self.get_possible_lookupname(linux_libraries, linux_libid)
            if should_skip_library_for_windows(lookupname, nightly_libraries_for_language[libid]):
                continue

            if lookupname not in reorganised_libs:
                reorganised_libs[lookupname] = set()

            logger.debug(f"Mapping {linux_libid} to {lookupname}")
            reorganised_libs[lookupname].add(linux_libid)

        for linux_libid, yamllibids in reorganised_libs.items():
            all_ids.append(linux_libid)
            linux_lib = linux_libraries[linux_libid]

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
                if yamllibid in libraries_for_language:
                    if "targets" in libraries_for_language[yamllibid]:
                        for libver in libraries_for_language[yamllibid]["targets"]:
                            all_libver_ids.append(self.get_libverid(libver))
                if yamllibid in nightly_libraries_for_language:
                    if not isinstance(nightly_libraries_for_language[yamllibid], dict):
                        continue
                    if "targets" in nightly_libraries_for_language[yamllibid]:
                        for libver in nightly_libraries_for_language[yamllibid]["targets"]:
                            all_libver_ids.append(self.get_libverid(libver))

            versions_property_key = generate_library_property_key(linux_libid, "versions")
            libverprops += f"{versions_property_key}="
            libverprops += ":".join(all_libver_ids) + "\n"

            prefix = generate_library_property_key(linux_libid, "")
            prefix = prefix.rstrip(".")
            libverprops += self.get_link_props(linux_lib, prefix)

            for yamllibid in yamllibids:
                if yamllibid in libraries_for_language:
                    if "targets" in libraries_for_language[yamllibid]:
                        for libver in libraries_for_language[yamllibid]["targets"]:
                            all_libver_ids.append(self.get_libverid(libver))

                        for libver in libraries_for_language[yamllibid]["targets"]:
                            libverid = self.get_libverid(libver)
                            libvername = self.get_libvername(libver)
                            version_property_key = generate_version_property_key(linux_libid, libverid, "version")
                            libverprops += f"{version_property_key}={libvername}\n"
                            linux_lib_version = get_specific_library_version_details(
                                linux_libraries, linux_libid, libverid
                            )
                            if not linux_lib_version:
                                linux_lib_version = get_specific_library_version_details(
                                    linux_libraries, linux_libid, libvername
                                )

                            prefix = generate_version_property_key(linux_libid, libverid, "")
                            prefix = prefix.rstrip(".")
                            libverprops += self.get_link_props(linux_lib_version, prefix)

                if yamllibid in nightly_libraries_for_language:
                    if not isinstance(nightly_libraries_for_language[yamllibid], dict):
                        continue
                    if "targets" in nightly_libraries_for_language[yamllibid]:
                        for libver in nightly_libraries_for_language[yamllibid]["targets"]:
                            all_libver_ids.append(self.get_libverid(libver))

                        for libver in nightly_libraries_for_language[yamllibid]["targets"]:
                            libverid = self.get_libverid(libver)
                            libvername = self.get_libvername(libver)
                            version_property_key = generate_version_property_key(linux_libid, libverid, "version")
                            libverprops += f"{version_property_key}={libvername}\n"
                            linux_lib_version = get_specific_library_version_details(
                                linux_libraries, linux_libid, libverid
                            )
                            if not linux_lib_version:
                                linux_lib_version = get_specific_library_version_details(
                                    linux_libraries, linux_libid, libvername
                                )

                            prefix = generate_version_property_key(linux_libid, libverid, "")
                            prefix = prefix.rstrip(".")
                            libverprops += self.get_link_props(linux_lib_version, prefix)

            properties_txt += libverprops + "\n"

        header_properties_txt = "libs=" + ":".join(all_ids) + "\n\n"

        return header_properties_txt + properties_txt

    @classmethod
    def load_library_yaml_section(cls, language):
        """Load libraries.yaml and return the specified language section."""
        yaml_dir = Path(__file__).parent.parent / "yaml"
        library_yaml = cls(str(yaml_dir))

        # Ensure language section exists
        if language not in library_yaml.yaml_doc["libraries"]:
            library_yaml.yaml_doc["libraries"][language] = {}

        return library_yaml, library_yaml.yaml_doc["libraries"][language]
