import os
import yaml

from pathlib import Path
from typing import List

from lib.library_platform import LibraryPlatform
from lib.amazon_properties import get_properties_compilers_and_libraries, get_specific_library_version_details
from lib.rust_crates import TopRustCrates

from lib.config_safe_loader import ConfigSafeLoader


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
        if not "rust" in self.yaml_doc["libraries"]:
            self.yaml_doc["libraries"]["rust"] = dict()

        libraries_for_language = self.yaml_doc["libraries"]["rust"]
        if libid in libraries_for_language:
            if not libversion in libraries_for_language[libid]["targets"]:
                libraries_for_language[libid]["targets"].append(libversion)
        else:
            libraries_for_language[libid] = dict(type="cratesio", build_type="cargo", targets=[libversion])

    def get_ce_properties_for_rust_libraries(self):
        all_ids: List[str] = []
        properties_txt = ""

        libraries_for_language = self.yaml_doc["libraries"]["rust"]
        for libid in libraries_for_language:
            all_ids.append(libid)

            all_libver_ids: List[str] = []

            for libver in libraries_for_language[libid]["targets"]:
                all_libver_ids.append(libver.replace(".", ""))

            libverprops = f"libs.{libid}.name={libid}\n"
            libverprops += f"libs.{libid}.url=https://crates.io/crates/{libid}\n"
            libverprops += f"libs.{libid}.versions="
            libverprops += ":".join(all_libver_ids) + "\n"

            for libver in libraries_for_language[libid]["targets"]:
                libverid = libver.replace(".", "")
                libverprops += f"libs.{libid}.versions.{libverid}.version={libver}\n"
                underscore_lib = libid.replace("-", "_")
                libverprops += f"libs.{libid}.versions.{libverid}.path=lib{underscore_lib}.rlib\n"

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
            libverid = libver["name"].replace(".", "")
        else:
            libverid = libver.replace(".", "")
        return libverid

    def get_libvername(self, libver) -> str:
        if isinstance(libver, dict) and "name" in libver:
            libverid = libver["name"]
        else:
            libverid = libver
        return libverid

    def get_possible_lookupname(self, logger, linux_libraries, libid) -> str:
        for libkey in linux_libraries:
            lib = linux_libraries[libkey]
            if "lookupname" in lib:
                if libid == lib["lookupname"]:
                    logger.info(lib)
                    return lib["id"]

            if "versionprops" in lib:
                for libverid in lib["versionprops"]:
                    libver = lib["versionprops"][libverid]
                    if "lookupname" in libver:
                        if libid == libver["lookupname"]:
                            return libver["id"]

        return libid

    def get_ce_properties_for_cpp_windows_libraries(self, logger):
        all_ids: List[str] = []
        properties_txt = ""

        [_, linux_libraries] = get_properties_compilers_and_libraries("c++", logger, LibraryPlatform.Linux, False)

        libraries_for_language = self.yaml_doc["libraries"]["c++"]
        for libid in libraries_for_language:
            all_ids.append(libid)

            all_libver_ids: List[str] = []

            linuxlibid = libid
            if libid not in linux_libraries:
                linuxlibid = self.get_possible_lookupname(logger, linux_libraries, libid)

            linux_lib = linux_libraries[linuxlibid]

            if "targets" not in libraries_for_language[libid]:
                logger.error(f"Library {libid} does not have a 'targets' field.")
                continue

            for libver in libraries_for_language[libid]["targets"]:
                all_libver_ids.append(self.get_libverid(libver))

            libname = libid
            if "name" in linux_lib:
                libname = linux_lib["name"]

            libverprops = f"libs.{libid}.name={libname}\n"
            # libverprops += f"libs.{libid}.url=https://crates.io/crates/{libid}\n"
            libverprops += f"libs.{libid}.packagedheaders=true\n"
            libverprops += f"libs.{libid}.versions="
            libverprops += ":".join(all_libver_ids) + "\n"

            if linux_lib and "staticliblink" in linux_lib:
                if linux_lib["staticliblink"]:
                    linklist = ":".join(linux_lib["staticliblink"])
                    libverprops += f"libs.{libid}.staticliblink={linklist}\n"
            if linux_lib and "sharedliblink" in linux_lib:
                if linux_lib["sharedliblink"]:
                    linklist = ":".join(linux_lib["sharedliblink"])
                    libverprops += f"libs.{libid}.sharedliblink={linklist}\n"
            if linux_lib and "dependencies" in linux_lib:
                if linux_lib["dependencies"]:
                    linklist = ":".join(linux_lib["dependencies"])
                    libverprops += f"libs.{libid}.dependencies={linklist}\n"

            for libver in libraries_for_language[libid]["targets"]:
                libverid = self.get_libverid(libver)
                libvername = self.get_libvername(libver)
                libverprops += f"libs.{libid}.versions.{libverid}.version={libvername}\n"
                linux_lib_version = get_specific_library_version_details(linux_libraries, libid, libverid)
                if not linux_lib_version:
                    linux_lib_version = get_specific_library_version_details(linux_libraries, libid, libvername)

                if linux_lib_version:
                    if linux_lib_version["staticliblink"]:
                        linklist = ":".join(linux_lib_version["staticliblink"])
                        libverprops += f"libs.{libid}.versions.{libverid}.staticliblink={linklist}\n"
                    if linux_lib_version["sharedliblink"]:
                        linklist = ":".join(linux_lib_version["sharedliblink"])
                        libverprops += f"libs.{libid}.versions.{libverid}.sharedliblink={linklist}\n"
                    if linux_lib_version["dependencies"]:
                        linklist = ":".join(linux_lib_version["dependencies"])
                        libverprops += f"libs.{libid}.versions.{libverid}.dependencies={linklist}\n"
                else:
                    logger.warning(f"Library {libid} version {libverid} not found in Linux properties.")

                # underscore_lib = libid.replace("-", "_")
                # libverprops += f"libs.{libid}.versions.{libverid}.path=lib{underscore_lib}.rlib\n"

            properties_txt += libverprops + "\n"

        header_properties_txt = "libs=" + ":".join(all_ids) + "\n\n"

        return header_properties_txt + properties_txt
