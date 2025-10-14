from __future__ import annotations

import os
import re
import urllib.parse
from collections import defaultdict
from typing import Any

import requests

from lib.installation_context import FetchFailure
from lib.library_platform import LibraryPlatform


def get_specific_library_version_details(libraries, libid, library_version):
    if "versionprops" in libraries[libid]:
        for verid in libraries[libid]["versionprops"]:
            version_props = libraries[libid]["versionprops"][verid]
            if version_props["version"] == library_version or version_props["lookupversion"] == library_version:
                return version_props

    return False


COMPILEROPT_RE = re.compile(r"(\w*)\.(.*)\.(\w*)")


def get_properties_compilers_and_libraries(language, logger, platform: LibraryPlatform, filter_binary_support: bool):
    _compilers: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    _libraries: dict[str, dict[str, Any]] = defaultdict(lambda: {})

    encoded_language = urllib.parse.quote(language)

    if platform == LibraryPlatform.Linux:
        url = f"https://raw.githubusercontent.com/compiler-explorer/compiler-explorer/main/etc/config/{encoded_language}.amazon.properties"
    elif platform == LibraryPlatform.Windows:
        url = f"https://raw.githubusercontent.com/compiler-explorer/compiler-explorer/main/etc/config/{encoded_language}.amazonwin.properties"
    else:
        raise RuntimeError("Unsupported platform")

    request = requests.get(url, timeout=30)
    if not request.ok:
        raise FetchFailure(f"Fetch failure for {url}: {request}")
    lines = request.text.splitlines(keepends=False)

    if platform == LibraryPlatform.Windows and "libs=\n" in request.text:
        # Windows properties file is missing the libs section, so we need to fetch the Linux one to kickstart Windows libraries
        #  but technically it's better to always supply enough information in the yaml file, so this is a workaround
        request = requests.get(
            f"https://raw.githubusercontent.com/compiler-explorer/compiler-explorer/main/etc/config/{encoded_language}.amazon.properties",
            timeout=30,
        )
        if not request.ok:
            raise FetchFailure(f"Fetch failure for {url}: {request}")
        lines += request.text[request.text.index("libs=") :].splitlines(keepends=False)

    logger.debug("Reading properties for groups")
    groups: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    for line in lines:
        if line.startswith("group."):
            keyval = line.split("=", 1)
            key = keyval[0].split(".")
            val = keyval[1]
            group = key[1]

            if key[2] == "compilers":
                groups[group]["compilers"] = val.split(":")
            elif key[2] == "options":
                groups[group]["options"] = val
            elif key[2] == "compilerType":
                groups[group]["compilerType"] = val
            elif key[2] == "supportsBinary":
                groups[group]["supportsBinary"] = val == "true"
            elif key[2] == "ldPath":
                groups[group]["ldPath"] = val
            elif key[2] == "libPath":
                groups[group]["libPath"] = val
            elif key[2] == "includePath":
                groups[group]["includePath"] = val
        elif line.startswith("libs."):
            keyval = line.split("=", 1)
            key = keyval[0].split(".")
            val = keyval[1]
            libid = key[1]

            _libraries[libid]["id"] = libid

            if key[2] == "description":
                _libraries[libid]["description"] = val
            elif key[2] == "name":
                _libraries[libid]["name"] = val
            elif key[2] == "url":
                _libraries[libid]["url"] = val
            elif key[2] == "liblink":
                _libraries[libid]["liblink"] = val.split(":")
            elif key[2] == "staticliblink":
                _libraries[libid]["staticliblink"] = val.split(":")
            elif key[2] == "lookupname":
                _libraries[libid]["lookupname"] = val
            elif key[2] == "versions":
                if len(key) > 3:
                    versionid = key[3]
                    if "versionprops" not in _libraries[libid]:
                        _libraries[libid]["versionprops"] = {}
                    if versionid not in _libraries[libid]["versionprops"]:
                        _libraries[libid]["versionprops"][versionid] = defaultdict(lambda: [])
                    if len(key) > 4:
                        if key[4] == "version":
                            _libraries[libid]["versionprops"][versionid][key[4]] = val
                        if key[4] == "lookupversion":
                            _libraries[libid]["versionprops"][versionid][key[4]] = val
                        if key[4] == "path":
                            _libraries[libid]["versionprops"][versionid][key[4]] = val.split(":")
                        if key[4] == "libpath":
                            _libraries[libid]["versionprops"][versionid][key[4]] = val.split(":")
                        if key[4] == "staticliblink":
                            _libraries[libid]["versionprops"][versionid][key[4]] = val.split(":")
                        if key[4] == "liblink":
                            _libraries[libid]["versionprops"][versionid][key[4]] = val.split(":")
                        if key[4] == "lookupname":
                            _libraries[libid]["versionprops"][versionid][key[4]] = val
                else:
                    _libraries[libid]["versions"] = val

    logger.debug("Setting default values for compilers")
    for group, group_data in groups.items():
        for compiler in group_data["compilers"]:
            if "&" in compiler:
                subgroupname = compiler[1:]
                if "options" not in groups[subgroupname] and "options" in group_data:
                    groups[subgroupname]["options"] = group_data["options"]
                if "compilerType" not in groups[subgroupname] and "compilerType" in group_data:
                    groups[subgroupname]["compilerType"] = group_data["compilerType"]
                if "supportsBinary" not in groups[subgroupname] and "supportsBinary" in group_data:
                    groups[subgroupname]["supportsBinary"] = group_data["supportsBinary"]
                if "ldPath" not in groups[subgroupname] and "ldPath" in group_data:
                    groups[subgroupname]["ldPath"] = group_data["ldPath"]
                if "libPath" not in groups[subgroupname] and "libPath" in group_data:
                    groups[subgroupname]["libPath"] = group_data["libPath"]
                if "includePath" not in groups[subgroupname] and "includePath" in group_data:
                    groups[subgroupname]["includePath"] = group_data["includePath"]
            else:
                _compilers[compiler]["options"] = group_data.get("options", "")
                _compilers[compiler]["compilerType"] = group_data.get("compilerType", "")
                _compilers[compiler]["supportsBinary"] = group_data.get("supportsBinary", True)
                _compilers[compiler]["ldPath"] = group_data.get("ldPath", "")
                _compilers[compiler]["libPath"] = group_data.get("libPath", "")
                _compilers[compiler]["includePath"] = group_data.get("includePath", "")
                _compilers[compiler]["group"] = group

    logger.debug("Reading properties for compilers")
    for line in lines:
        if line.startswith("compiler."):
            compilerkey, compilervalue = line.split("=", 1)
            matches = COMPILEROPT_RE.match(compilerkey)
            if not matches:
                raise RuntimeError(f"Not a valid compiler? {compilerkey}={compilervalue}")
            compiler = matches[2]
            compilerid = matches[3]

            if key == "supportsBinary":
                _compilers[compiler][compilerid] = compilervalue == "true"
            else:
                _compilers[compiler][compilerid] = compilervalue

    if filter_binary_support:
        logger.debug("Removing compilers that are not available or do not support binaries")
        keys_to_remove = set()
        for compiler, compiler_data in _compilers.items():
            if "supportsBinary" in compiler_data and not compiler_data["supportsBinary"]:
                logger.debug("%s does not supportsBinary", compiler)
                keys_to_remove.add(compiler)
            elif "compilerType" in compiler_data and compiler_data["compilerType"] == "wine-vc":
                keys_to_remove.add(compiler)
                logger.debug("%s is wine", compiler)
            elif "exe" in compiler_data:
                exe = compiler_data["exe"]
                if not os.path.exists(exe):
                    keys_to_remove.add(compiler)
                    logger.debug("%s does not exist (looked for %s)", compiler, exe)
            else:
                keys_to_remove.add(compiler)
                logger.debug("%s didn't have the required config keys", compiler)

        for compiler in keys_to_remove:
            logger.debug("removing %s", compiler)
            del _compilers[compiler]

    return [_compilers, _libraries]
