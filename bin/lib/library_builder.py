from __future__ import annotations

import contextlib
import csv
import glob
import itertools
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.parse
from collections import defaultdict
from collections.abc import Callable, Generator
from enum import Enum, unique
from logging import Logger
from pathlib import Path
from typing import Any, TextIO, TypedDict

import botocore
import requests
from urllib3.exceptions import ProtocolError

from lib.amazon import get_ssm_param
from lib.amazon_properties import get_properties_compilers_and_libraries, get_specific_library_version_details
from lib.binary_info import BinaryInfo
from lib.installation_context import FetchFailure, PostFailure
from lib.library_build_config import LibraryBuildConfig
from lib.library_build_history import LibraryBuildHistory
from lib.library_platform import LibraryPlatform
from lib.staging import StagingDir

_TIMEOUT = 600
compiler_popularity_treshhold = 1000
popular_compilers: dict[str, Any] = defaultdict(lambda: [])

disable_clang_libcpp = [
    "clang30",
    "clang31",
    "clang32",
    "clang33",
    "clang341",
    "clang350",
    "clang351",
    "clang352",
    "clang37x",
    "clang36x",
    "clang371",
    "clang380",
    "clang381",
    "clang390",
    "clang391",
    "clang400",
    "clang401",
]
disable_clang_32bit = disable_clang_libcpp.copy()
disable_clang_libcpp += ["clang_lifetime"]
disable_compiler_ids = [
    "avrg454",
    "icc1301",
    "icc16",
    "icc17",
    "icc18",
    "icc19",
    "icc191",
    "icc202112",
    "icc202120",
    "icc202130",
    "icc202140",
    "icc202150",
    "icc202160",
    "icc202170",
    "icc202171",
    "icc202180",
    "icc202190",
    "icc2021100",
]

_propsandlibs: dict[str, Any] = defaultdict(lambda: [])
_supports_x86: dict[str, Any] = defaultdict(lambda: [])
_compiler_support_output: dict[str, Any] = defaultdict(lambda: [])

GITCOMMITHASH_RE = re.compile(r"^(\w*)\s.*")


def _quote(string: str) -> str:
    return f'"{string}"'


class ConanSearchEntry(TypedDict, total=False):
    """A single entry in a Conan /v1/.../search response, keyed by package_id at the top level."""

    settings: dict[str, str]
    options: dict[str, str]
    full_requires: list[str]
    recipe_hash: str


type PossibleBuilds = dict[str, ConanSearchEntry]


def match_conan_settings(target: dict[str, str], candidate: dict[str, str]) -> bool:
    """Match a target settings dict against a candidate's settings.

    Ported from compiler-explorer/lib/buildenvsetup/ceconan.ts findMatchingHash. Each rule
    checks the *candidate's* value for the key under inspection, so a partially-flagged
    headeronly entry (only some sub-settings set to 'headeronly') is matched key-by-key
    rather than via a single up-front predicate. Behavioural rules:
    - 'headeronly' / 'cshared' value on compiler/compiler.version matches any target value.
    - 'headeronly' / 'cshared' value on compiler.libcxx (only when the candidate's
      `settings.compiler` is itself 'headeronly' or 'cshared') matches any target libcxx;
      'headeronly' also matches any arch.
    - stdver is treated as a wildcard: pre-c++11 ABI breakage aside, compiler.version
      already discriminates incompatible cases.
    - All other keys must compare equal.
    """
    candidate_compiler = candidate.get("compiler", "")
    parent_is_placeholder = candidate_compiler in ("headeronly", "cshared")

    for key, val in target.items():
        if key in ("compiler", "compiler.version") and candidate.get(key) in ("headeronly", "cshared"):
            continue
        if key == "compiler.libcxx" and parent_is_placeholder:
            continue
        if key == "arch" and candidate_compiler == "headeronly":
            continue
        if key == "stdver":
            continue
        if val != candidate.get(key, ""):
            return False
    return True


def conan_search_url(libname: str, target_name: str) -> str:
    encoded_lib = urllib.parse.quote(libname, safe="")
    encoded_ver = urllib.parse.quote(target_name, safe="")
    return f"{conanserver_url}/v1/conans/{encoded_lib}/{encoded_ver}/{encoded_lib}/{encoded_ver}/search"


def fetch_possible_builds(
    libname: str,
    target_name: str,
    fetcher: Callable[[str], requests.Response | None],
    logger: Logger,
) -> PossibleBuilds:
    """Fetch and parse the conan-server /search response for a (libname, target_name).

    `fetcher` is a one-argument callable taking the URL and returning a Response (or None to
    signal a request that failed all retries). Each builder class supplies its own fetcher
    so it can pick its retry strategy (resil_get vs raw http_session.get).

    404 means no packages have been uploaded yet for this lib/version, and is the natural
    starting state for new libraries -- return an empty dict.
    """
    url = conan_search_url(libname, target_name)
    try:
        response = fetcher(url)
    except requests.RequestException as e:
        raise FetchFailure(f"Conan search request failed for {libname}/{target_name}: {e}") from e

    if response is None:
        raise FetchFailure(f"Conan search request failed for {libname}/{target_name}")
    if response.status_code == 404:
        logger.debug("No uploaded builds yet for %s/%s", libname, target_name)
        return {}
    if not response.ok:
        raise FetchFailure(f"Conan search returned {response.status_code} for {libname}/{target_name}")

    try:
        payload = response.json()
    except ValueError as e:
        raise FetchFailure(f"Conan search returned non-JSON for {libname}/{target_name}") from e
    if not isinstance(payload, dict):
        raise FetchFailure(f"Conan search returned non-object JSON for {libname}/{target_name}")
    return payload


def find_matching_package_id(possible_builds: PossibleBuilds, target: dict[str, str]) -> str | None:
    """Return the first package_id in `possible_builds` whose settings match `target`."""
    for package_id, entry in possible_builds.items():
        settings = entry.get("settings", {}) if isinstance(entry, dict) else {}
        if match_conan_settings(target, settings):
            return package_id
    return None


class FailedBuildRecord(TypedDict, total=False):
    """A single row from /failedbuilds: a known-failed (compiler, ...) tuple for some lib/version."""

    compiler: str
    compiler_version: str
    arch: str
    libcxx: str
    compiler_flags: str
    commithash: str


type FailedBuilds = list[FailedBuildRecord]


def failed_builds_url(libname: str, target_name: str) -> str:
    encoded_lib = urllib.parse.quote(libname, safe="")
    encoded_ver = urllib.parse.quote(target_name, safe="")
    return f"{conanserver_url}/failedbuilds/{encoded_lib}/{encoded_ver}"


def fetch_failed_builds(
    libname: str,
    target_name: str,
    fetcher: Callable[[str], requests.Response | None],
    logger: Logger,
) -> FailedBuilds:
    """Fetch and parse the conan-proxy /failedbuilds response for a (libname, target_name).

    404 means no failures recorded yet; non-2xx and malformed payloads raise FetchFailure.
    """
    url = failed_builds_url(libname, target_name)
    try:
        response = fetcher(url)
    except requests.RequestException as e:
        raise FetchFailure(f"Failed-builds request failed for {libname}/{target_name}: {e}") from e

    if response is None:
        raise FetchFailure(f"Failed-builds request failed for {libname}/{target_name}")
    if response.status_code == 404:
        logger.debug("No recorded failures for %s/%s", libname, target_name)
        return []
    if not response.ok:
        raise FetchFailure(f"Failed-builds returned {response.status_code} for {libname}/{target_name}")

    try:
        payload = response.json()
    except ValueError as e:
        raise FetchFailure(f"Failed-builds returned non-JSON for {libname}/{target_name}") from e
    if not isinstance(payload, list):
        raise FetchFailure(f"Failed-builds returned non-array JSON for {libname}/{target_name}")
    return payload


def match_failed_build(
    records: FailedBuilds,
    build_params: dict[str, Any],
    current_commit_hash: str | None,
) -> bool:
    """Return True iff some record matches build_params on the discriminator columns.

    Discriminators: compiler, compiler_version, arch, libcxx, flagcollection. When
    `current_commit_hash` is given, the record's commithash must match too -- a failure
    against a different commit is treated as stale so the next build can retry.
    """
    target_compiler = build_params.get("compiler", "")
    target_version = build_params.get("compiler_version", "")
    target_arch = build_params.get("arch", "")
    target_libcxx = build_params.get("libcxx", "")
    target_flags = build_params.get("flagcollection", "")

    for r in records:
        if (
            r.get("compiler", "") == target_compiler
            and r.get("compiler_version", "") == target_version
            and r.get("arch", "") == target_arch
            and r.get("libcxx", "") == target_libcxx
            and r.get("compiler_flags", "") == target_flags
        ):
            if current_commit_hash is None:
                return True
            return r.get("commithash", "") == current_commit_hash
    return False


def build_target_settings(buildparams: dict[str, Any]) -> dict[str, str]:
    """Translate current_buildparameters_obj keys into conan settings dotted form.

    Uses .get(key, "") rather than indexing because the source object may be a defaultdict
    with a list factory; a missing key would otherwise mutate the dict and produce a
    non-string value that breaks equality matching.
    """
    return {
        "os": buildparams.get("os", ""),
        "build_type": buildparams.get("buildtype", ""),
        "compiler": buildparams.get("compiler", ""),
        "compiler.version": buildparams.get("compiler_version", ""),
        "compiler.libcxx": buildparams.get("libcxx", ""),
        "arch": buildparams.get("arch", ""),
        "stdver": buildparams.get("stdver", ""),
        "flagcollection": buildparams.get("flagcollection", ""),
    }


@unique
class BuildStatus(Enum):
    Ok = 0
    Failed = 1
    Skipped = 2
    TimedOut = 3


build_timeout = 1200

conanserver_url = "https://conan.compiler-explorer.com"


@contextlib.contextmanager
def open_script(script: Path) -> Generator[TextIO, None, None]:
    with script.open("w", encoding="utf-8") as f:
        yield f
    script.chmod(0o755)


class LibraryBuilder:
    def __init__(
        self,
        logger,
        language: str,
        libname: str,
        target_name: str,
        sourcefolder: str,
        install_context,
        buildconfig: LibraryBuildConfig,
        popular_compilers_only: bool,
        platform: LibraryPlatform,
    ):
        self.logger = logger
        self.language = language
        self.libname = libname
        self.buildconfig = buildconfig
        self.install_context = install_context
        self.sourcefolder = sourcefolder
        self.target_name = target_name
        self.forcebuild = False
        self.current_buildparameters_obj: dict[str, Any] = defaultdict(lambda: [])
        self.current_buildparameters: list[str] = []
        self.needs_uploading = 0
        self.libid = self.libname  # TODO: CE libid might be different from yaml libname
        self.conanserverproxy_token = None
        self.current_commit_hash = ""
        self.platform = platform
        self._possible_builds: PossibleBuilds | None = None
        self._failed_builds: FailedBuilds | None = None
        self._annotations_cache: dict[str, dict] = {}
        self.http_session = requests.Session()

        self.history = LibraryBuildHistory(self.logger)

        if self.language in _propsandlibs:
            [self.compilerprops, self.libraryprops] = _propsandlibs[self.language]
        else:
            [self.compilerprops, self.libraryprops] = get_properties_compilers_and_libraries(
                self.language, self.logger, self.platform, True
            )
            _propsandlibs[self.language] = [self.compilerprops, self.libraryprops]

        self.check_compiler_popularity = popular_compilers_only

        self.script_filename = "cebuild.sh"
        if self.platform == LibraryPlatform.Windows:
            self.script_filename = "cebuild.ps1"

        if self.platform == LibraryPlatform.Windows:
            self.buildconfig.package_install = True

        self.completeBuildConfig()

    def completeBuildConfig(self):
        if "description" in self.libraryprops[self.libid]:
            self.buildconfig.description = self.libraryprops[self.libid]["description"]
        if "name" in self.libraryprops[self.libid]:
            self.buildconfig.description = self.libraryprops[self.libid]["name"]
        if "url" in self.libraryprops[self.libid]:
            self.buildconfig.url = self.libraryprops[self.libid]["url"]

        if "staticliblink" in self.libraryprops[self.libid]:
            self.buildconfig.staticliblink = list(
                set(self.buildconfig.staticliblink + self.libraryprops[self.libid]["staticliblink"])
            )

        if "liblink" in self.libraryprops[self.libid]:
            self.buildconfig.sharedliblink = list(
                set(self.buildconfig.sharedliblink + self.libraryprops[self.libid]["liblink"])
            )

        specificVersionDetails = get_specific_library_version_details(self.libraryprops, self.libid, self.target_name)
        if specificVersionDetails:
            if "staticliblink" in specificVersionDetails:
                self.buildconfig.staticliblink = list(
                    set(self.buildconfig.staticliblink + specificVersionDetails["staticliblink"])
                )

            if "liblink" in specificVersionDetails:
                self.buildconfig.sharedliblink = list(
                    set(self.buildconfig.sharedliblink + specificVersionDetails["liblink"])
                )

        if self.buildconfig.lib_type == "headeronly":
            if self.buildconfig.staticliblink != []:
                self.buildconfig.lib_type = "static"
            if self.buildconfig.sharedliblink != []:
                self.buildconfig.lib_type = "shared"

        if self.buildconfig.lib_type == "static":
            if self.buildconfig.staticliblink == []:
                self.buildconfig.staticliblink = [f"{self.libname}"]
        elif self.buildconfig.lib_type == "shared":
            if self.buildconfig.sharedliblink == []:
                self.buildconfig.sharedliblink = [f"{self.libname}"]
        elif self.buildconfig.lib_type == "cshared":
            if self.buildconfig.sharedliblink == []:
                self.buildconfig.sharedliblink = [f"{self.libname}"]

        if self.platform == LibraryPlatform.Windows:
            self.buildconfig.package_install = True

        alternatelibs = []
        for lib in self.buildconfig.staticliblink:
            if lib.endswith("d") and lib[:-1] not in self.buildconfig.staticliblink:
                alternatelibs += [lib[:-1]]
            else:
                if f"{lib}d" not in self.buildconfig.staticliblink:
                    alternatelibs += [f"{lib}d"]

        self.buildconfig.staticliblink += alternatelibs

        alternatelibs = []
        for lib in self.buildconfig.sharedliblink:
            if lib.endswith("d") and lib[:-1] not in self.buildconfig.sharedliblink:
                alternatelibs += [lib[:-1]]
            else:
                if f"{lib}d" not in self.buildconfig.sharedliblink:
                    alternatelibs += [f"{lib}d"]

        self.buildconfig.sharedliblink += alternatelibs

    def getToolchainPathFromOptions(self, options):
        match = re.search(r"--gcc-toolchain=(\S*)", options)
        if match:
            return match[1]
        else:
            match = re.search(r"--gxx-name=(\S*)", options)
            if match:
                toolchainpath = Path(match[1]).parent / ".."
                return os.path.abspath(toolchainpath)
        return False

    def getSysrootPathFromOptions(self, options):
        match = re.search(r"--sysroot=(\S*)", options)
        if match:
            return match[1]
        return False

    def getStdVerFromOptions(self, options):
        match = re.search(r"-std=(\S*)", options)
        if match:
            return match[1]
        return False

    def getStdLibFromOptions(self, options):
        match = re.search(r"-stdlib=(\S*)", options)
        if match:
            return match[1]
        return False

    def getTargetFromOptions(self, options):
        match = re.search(r"-target (\S*)", options)
        if match:
            return match[1]
        return False

    def getDefaultTargetFromCompiler(self, exe):
        try:
            return subprocess.check_output([exe, "-dumpmachine"]).decode("utf-8", "ignore").strip()
        except:  # noqa: E722
            return False

    def get_compiler_support_output(self, exe, compilerType, ldPath):
        if exe in _compiler_support_output:
            return _compiler_support_output[exe]

        fullenv = os.environ
        fullenv["LD_LIBRARY_PATH"] = ldPath
        output = ""

        if not compilerType or compilerType == "win32-mingw-gcc":
            if "icc" in exe:
                output = subprocess.check_output([exe, "--help"], env=fullenv).decode("utf-8", "ignore")
            else:
                if "zapcc" not in exe and "icpx" not in exe:
                    try:
                        output = subprocess.check_output([exe, "--target-help"], env=fullenv).decode("utf-8", "ignore")
                    except subprocess.CalledProcessError as e:
                        output = e.output.decode("utf-8", "ignore")
        elif compilerType == "clang" or compilerType == "win32-mingw-clang":
            folder = os.path.dirname(exe)
            llcexe = os.path.join(folder, "llc")
            if self.platform == LibraryPlatform.Windows:
                llcexe += ".exe"
            if os.path.exists(llcexe):
                try:
                    output = subprocess.check_output([llcexe, "--version"], env=fullenv).decode("utf-8", "ignore")
                except subprocess.CalledProcessError as e:
                    output = e.output.decode("utf-8", "ignore")
        elif compilerType == "win32-vc":
            # note: cl.exe does not have a --version flag or target flags, but it displays the version and target in stderr
            output = subprocess.check_output([exe], stderr=subprocess.STDOUT, env=fullenv).decode("utf-8", "ignore")

        _compiler_support_output[exe] = output

        return output

    def get_support_check_text(self, exe, compilerType, arch):
        if "icc" in exe:
            if arch == "x86":
                return "-m32"
            elif arch == "x86_64":
                return "-m64"
        elif compilerType == "win32-vc":
            if arch == "x86":
                return "for x86"
            elif arch == "x86_64":
                return "for x64"
            elif arch == "arm64":
                return "for ARM64"

        return arch

    def does_compiler_support(self, exe, compilerType, arch, options, ldPath):
        fixedTarget = self.getTargetFromOptions(options)
        if fixedTarget:
            return fixedTarget == arch

        output = self.get_compiler_support_output(exe, compilerType, ldPath)
        if not compilerType:
            if "icpx" in exe:
                return arch == "x86" or arch == "x86_64"
            elif "zapcc" in exe:
                return arch == "x86" or arch == "x86_64"

        check_text = self.get_support_check_text(exe, compilerType, arch)
        if check_text in output:
            self.logger.debug(f"Compiler {exe} supports {arch}")
            return True
        else:
            self.logger.debug(f"Compiler {exe} does not support {arch}")
            return False

    def does_compiler_support_x86(self, exe, compilerType, options, ldPath):
        cachekey = f"{exe}|{options}"
        if cachekey not in _supports_x86:
            _supports_x86[cachekey] = self.does_compiler_support(exe, compilerType, "x86", options, ldPath)
        return _supports_x86[cachekey]

    def does_compiler_support_amd64(self, exe, compilerType, options, ldPath):
        return self.does_compiler_support(exe, compilerType, "x86_64", options, ldPath)

    def replace_optional_arg(self, arg, name, value):
        self.logger.debug(f"replace_optional_arg('{arg}', '{name}', '{value}')")
        optional = "%" + name + "?%"
        if optional in arg:
            return arg.replace(optional, value) if value else ""
        else:
            return arg.replace("%" + name + "%", value)

    def expand_make_arg(self, arg, compilerTypeOrGcc, buildtype, arch, stdver, stdlib):
        expanded = arg

        expanded = self.replace_optional_arg(expanded, "compilerTypeOrGcc", compilerTypeOrGcc)
        expanded = self.replace_optional_arg(expanded, "buildtype", buildtype)
        expanded = self.replace_optional_arg(expanded, "arch", arch)
        expanded = self.replace_optional_arg(expanded, "stdver", stdver)
        expanded = self.replace_optional_arg(expanded, "stdlib", stdlib)

        intelarch = ""
        if arch == "x86":
            intelarch = "ia32"
        elif arch == "x86_64":
            intelarch = "intel64"

        expanded = self.replace_optional_arg(expanded, "intelarch", intelarch)

        cmake_bool_windows = "OFF"
        cmake_bool_not_windows = "ON"
        if self.platform == LibraryPlatform.Windows:
            cmake_bool_windows = "ON"
            cmake_bool_not_windows = "OFF"

        expanded = self.replace_optional_arg(expanded, "cmake_bool_not_windows", cmake_bool_not_windows)
        expanded = self.replace_optional_arg(expanded, "cmake_bool_windows", cmake_bool_windows)

        return expanded

    def resil_post(self, url, json_data, headers=None):
        request = None
        retries = 3
        last_error = ""
        while retries > 0:
            try:
                if headers is not None:
                    request = self.http_session.post(url, data=json_data, headers=headers, timeout=_TIMEOUT)
                else:
                    request = self.http_session.post(
                        url, data=json_data, headers={"Content-Type": "application/json"}, timeout=_TIMEOUT
                    )

                retries = 0
            except ProtocolError as e:
                last_error = e
                retries = retries - 1
                time.sleep(1)

        if request is None:
            request = {"ok": False, "text": last_error}

        return request

    def resil_get(self, url: str, stream: bool, timeout: int, headers=None) -> requests.Response | None:
        request: requests.Response | None = None
        retries = 3
        while retries > 0:
            try:
                if headers is not None:
                    request = self.http_session.get(url, stream=stream, headers=headers, timeout=timeout)
                else:
                    request = self.http_session.get(
                        url, stream=stream, headers={"Content-Type": "application/json"}, timeout=timeout
                    )

                retries = 0
            except ProtocolError:
                retries = retries - 1
                time.sleep(1)

        return request

    def expand_build_script_line(
        self, line: str, buildos, buildtype, compilerTypeOrGcc, compiler, compilerexe, libcxx, arch, stdver, extraflags
    ):
        expanded = line

        expanded = self.replace_optional_arg(expanded, "buildos", buildos)
        expanded = self.replace_optional_arg(expanded, "buildtype", buildtype)
        expanded = self.replace_optional_arg(expanded, "compilerTypeOrGcc", compilerTypeOrGcc)
        expanded = self.replace_optional_arg(expanded, "compiler", compiler)
        expanded = self.replace_optional_arg(expanded, "compilerexe", compilerexe)
        expanded = self.replace_optional_arg(expanded, "libcxx", libcxx)
        expanded = self.replace_optional_arg(expanded, "arch", arch)
        expanded = self.replace_optional_arg(expanded, "stdver", stdver)
        expanded = self.replace_optional_arg(expanded, "extraflags", extraflags)

        return expanded

    def script_env(self, var_name: str, var_value: str):
        if self.platform == LibraryPlatform.Linux:
            return f'export {var_name}="{var_value}"\n'
        elif self.platform == LibraryPlatform.Windows:
            escaped_var_value = var_value.replace('"', '`"')
            return f'$env:{var_name}="{escaped_var_value}"\n'

    def script_addtoend_env(self, var_name: str, var_value: str):
        if self.platform == LibraryPlatform.Linux:
            return f'export {var_name}="{var_name}:{var_value}"\n'
        elif self.platform == LibraryPlatform.Windows:
            escaped_var_value = var_value.replace('"', '`"')
            return f'$env:{var_name}="$env:{var_name};{escaped_var_value}"\n'

    def writebuildscript(
        self,
        buildfolder,
        installfolder,
        sourcefolder,
        compiler,
        compileroptions,
        compilerexe,
        compilerType,
        toolchain,
        buildos,
        buildtype,
        arch,
        stdver,
        stdlib,
        flagscombination,
        ldPath,
        compiler_props,
    ):
        with open_script(Path(buildfolder) / self.script_filename) as f:
            compilerexecc = ""
            if self.platform == LibraryPlatform.Linux:
                f.write("#!/bin/sh\n\n")

                compilerexecc = compilerexe[:-2]
                if compilerexe.endswith("clang++"):
                    compilerexecc = f"{compilerexecc}"
                elif compilerexe.endswith("g++"):
                    compilerexecc = f"{compilerexecc}cc"
                elif compilerType == "edg":
                    compilerexecc = compilerexe

            elif self.platform == LibraryPlatform.Windows:
                compilerexecc = compilerexe.replace("++.exe", "")
                if compilerexe.endswith("clang++.exe"):
                    compilerexecc = f"{compilerexecc}.exe"
                elif compilerexe.endswith("g++.exe"):
                    compilerexecc = f"{compilerexecc}cc.exe"
                elif compilerType == "edg":
                    compilerexecc = compilerexe
                else:
                    if not compilerexecc.endswith(".exe"):
                        compilerexecc = compilerexecc + ".exe"

            f.write(self.script_env("CC", compilerexecc))
            f.write(self.script_env("CXX", compilerexe))

            is_msvc = compilerType == "win32-vc"

            libparampaths = []
            archflag = ""
            if is_msvc:
                libparampaths = compiler_props["libPath"].split(";")
            else:
                if not arch or arch == "x86_64":
                    # note: native arch for the compiler, so most of the time 64, but not always
                    if os.path.exists(f"{toolchain}/lib64"):
                        libparampaths.append(f"{toolchain}/lib64")
                        libparampaths.append(f"{toolchain}/lib")
                    else:
                        libparampaths.append(f"{toolchain}/lib")
                elif arch == "x86":
                    libparampaths.append(f"{toolchain}/lib")
                    if os.path.exists(f"{toolchain}/lib32"):
                        libparampaths.append(f"{toolchain}/lib32")

                    if compilerType == "clang" or compilerType == "win32-mingw-clang":
                        archflag = "-m32"
                    elif not compilerType or compilerType == "gcc" or compilerType == "win32-mingw-gcc":
                        archflag = "-march=i386 -m32"

            rpathflags = ""
            ldflags = ""
            if compilerType != "edg" and not is_msvc:
                for path in libparampaths:
                    rpathflags += f"-Wl,-rpath={path} "

            if is_msvc:
                f.write(self.script_env("INCLUDE", compiler_props["includePath"]))
                f.write(self.script_env("LIB", compiler_props["libPath"]))
                # extra path is needed for msvc, because .dll's are placed in the x64 path and not the other architectures
                #  somehow this is not a thing on CE, but it is an issue for when used with CMake
                x64path = Path(compilerexe).parent / "../x64"
                f.write(self.script_addtoend_env("PATH", os.path.abspath(x64path)))
            else:
                for path in libparampaths:
                    if path:
                        ldflags += f"-L{path} "

            ldlibpathsstr = ldPath.replace("${exePath}", os.path.dirname(compilerexe)).replace("|", ":")

            sysrootpath = self.getSysrootPathFromOptions(compileroptions)
            sysrootparam = ""
            if sysrootpath:
                sysrootparam = f'"-DCMAKE_SYSROOT={sysrootpath}"'

            target = self.getTargetFromOptions(compileroptions)
            triplearr = []
            if target:
                triplearr = target.split("-")
            else:
                if not is_msvc:
                    target = self.getDefaultTargetFromCompiler(compilerexecc)
                    if target:
                        triplearr = target.strip().split("-")
            shorttarget = ""
            boosttarget = ""
            boostabi = ""
            if len(triplearr) != 0:
                shorttarget = triplearr[0]
                if shorttarget == "aarch64":
                    boosttarget = "arm64"
                else:
                    boosttarget = shorttarget

                if "arm" in boosttarget:
                    boostabi = "aapcs"
                else:
                    boostabi = "sysv"

                if shorttarget == "x86_64" and arch == "x86":
                    boosttarget = "i386"

            f.write(self.script_env("LD_LIBRARY_PATH", ldlibpathsstr))
            f.write(self.script_env("LDFLAGS", f"{ldflags} {rpathflags}"))
            if self.platform == LibraryPlatform.Linux:
                f.write(self.script_env("NUMCPUS", "$(nproc)"))

            stdverflag = ""
            if stdver:
                stdverflag = f"-std={stdver}"

            stdlibflag = ""
            if stdlib and compilerType == "clang":
                libcxx = stdlib
                stdlibflag = f"-stdlib={stdlib}"
                if stdlibflag in compileroptions:
                    stdlibflag = ""
            else:
                libcxx = "libstdc++"

            extraflags = " ".join(x for x in flagscombination)

            compilerTypeOrGcc = compilerType or "gcc"

            if is_msvc:
                compileroptions = compileroptions.replace("/source-charset:utf-8", "")

            if boosttarget == "i386":
                compileroptions += " -latomic"

            cxx_flags = f"{compileroptions} {archflag} {stdverflag} {stdlibflag} {extraflags}"
            c_compileroptions = re.sub(r"-std=c\+\+\w+\s*", "", compileroptions).strip()
            c_flags = f"{c_compileroptions} {archflag} {extraflags}"
            asm_flags = f"{archflag}"

            expanded_configure_flags = [
                self.expand_make_arg(arg, compilerTypeOrGcc, buildtype, arch, stdver, stdlib)
                for arg in self.buildconfig.configure_flags
            ]
            configure_flags = " ".join(expanded_configure_flags)

            make_utility = self.buildconfig.make_utility

            if self.buildconfig.build_type == "cmake" or self.buildconfig.build_type == "none":
                expanded_cmake_args = [
                    self.expand_make_arg(arg, compilerTypeOrGcc, buildtype, arch, stdver, stdlib)
                    for arg in self.buildconfig.extra_cmake_arg
                ]

                if self.platform == LibraryPlatform.Windows:
                    expanded_cmake_args = expanded_cmake_args + ["-D", f'"CMAKE_C_COMPILER={compilerexecc}"']
                    expanded_cmake_args = expanded_cmake_args + ["-D", f'"CMAKE_CXX_COMPILER={compilerexe}"']

                extracmakeargs = " ".join(expanded_cmake_args)
                if compilerTypeOrGcc == "clang" and "--gcc-toolchain=" not in compileroptions:
                    toolchainparam = ""
                else:
                    toolchainparam = f'"-DCMAKE_CXX_COMPILER_EXTERNAL_TOOLCHAIN={toolchain}" "-DCMAKE_C_COMPILER_EXTERNAL_TOOLCHAIN={toolchain}"'

                targetparams = ""
                if target:
                    targetparams = f'"-DCMAKE_SYSTEM_PROCESSOR={shorttarget}" "-DCMAKE_CXX_COMPILER_TARGET={target}" "-DCMAKE_C_COMPILER_TARGET={target}" "-DCMAKE_ASM_COMPILER_TARGET={target}"'
                    if "boost" in self.libid:
                        targetparams += (
                            f' "-DBOOST_CONTEXT_ARCHITECTURE={boosttarget}" "-DBOOST_CONTEXT_ABI={boostabi}" '
                        )
                        if boosttarget == "i386":
                            cxx_flags += " -DBOOST_STACKTRACE_LIBCXX_RUNTIME_MAY_CAUSE_MEMORY_LEAK "
                            targetparams += (
                                ' "-DBOOST_IOSTREAMS_ENABLE_BZIP2=OFF" "-DBOOST_IOSTREAMS_ENABLE_LZMA=OFF" '
                                '"-DBOOST_IOSTREAMS_ENABLE_ZSTD=OFF" "-DBOOST_LOCALE_ENABLE_ICU=OFF" '
                            )

                generator = ""
                if self.platform == LibraryPlatform.Linux:
                    if make_utility == "ninja":
                        generator = "-GNinja"
                elif self.platform == LibraryPlatform.Windows:
                    generator = "-GNinja"

                for line in self.buildconfig.prebuild_script:
                    expanded_line = self.expand_build_script_line(
                        line,
                        buildos,
                        buildtype,
                        compilerTypeOrGcc,
                        compiler,
                        compilerexe,
                        libcxx,
                        arch,
                        stdver,
                        extraflags,
                    )
                    f.write(f"{expanded_line}\n")

                # Use appropriate CMAKE_*_FLAGS based on build type
                cmake_flags_suffix = "_DEBUG" if buildtype == "Debug" else "_RELEASE"
                cmakeline = (
                    f'cmake --install-prefix "{installfolder}" {generator} "-DCMAKE_VERBOSE_MAKEFILE=ON" '
                    f'{targetparams} "-DCMAKE_BUILD_TYPE={buildtype}" {toolchainparam} {sysrootparam} '
                    f'"-DCMAKE_CXX_FLAGS{cmake_flags_suffix}={cxx_flags}" "-DCMAKE_C_FLAGS{cmake_flags_suffix}={c_flags}" '
                    f'"-DCMAKE_ASM_FLAGS{cmake_flags_suffix}={asm_flags}" {extracmakeargs} {sourcefolder} '
                    f"> cecmakelog.txt 2>&1 || "
                    f"{{ echo 'cmake configure failed:' >&2; tail -200 cecmakelog.txt >&2; exit 1; }}\n"
                )
                self.logger.debug(cmakeline)
                f.write(cmakeline)

                par_args = []
                if self.platform == LibraryPlatform.Linux:
                    par_args = ["-j$NUMCPUS"]

                extramakeargs = " ".join(
                    par_args
                    + [
                        self.expand_make_arg(arg, compilerTypeOrGcc, buildtype, arch, stdver, stdlib)
                        for arg in self.buildconfig.extra_make_arg
                    ]
                )

                if len(self.buildconfig.make_targets) != 0:
                    if len(self.buildconfig.make_targets) == 1 and self.buildconfig.make_targets[0] == "all":
                        f.write(
                            f"cmake --build . {extramakeargs} > cemakelog_.txt 2>&1 || "
                            f"{{ echo 'cmake --build failed:' >&2; tail -200 cemakelog_.txt >&2; exit 1; }}\n"
                        )
                    else:
                        for lognum, target in enumerate(self.buildconfig.make_targets):
                            log_name = f"cemakelog_{lognum}.txt"
                            f.write(
                                f"cmake --build . {extramakeargs} --target={target} > {log_name} 2>&1 || "
                                f"{{ echo 'cmake --build {target} failed:' >&2; tail -200 {log_name} >&2; exit 1; }}\n"
                            )
                else:
                    lognum = 0
                    for lib in itertools.chain(self.buildconfig.staticliblink, self.buildconfig.sharedliblink):
                        f.write(f"cmake --build . {extramakeargs} --target={lib} > cemakelog_{lognum}.txt 2>&1\n")
                        lognum += 1

                    if self.platform == LibraryPlatform.Linux:
                        if len(self.buildconfig.staticliblink) != 0:
                            f.write("libsfound=$(find . -iname 'lib*.a')\n")
                        elif len(self.buildconfig.sharedliblink) != 0:
                            f.write("libsfound=$(find . -iname 'lib*.so*')\n")

                        f.write('if [ "$libsfound" = "" ]; then\n')
                        f.write(f"  cmake --build . {extramakeargs} > cemakelog_{lognum}.txt 2>&1\n")
                        f.write("fi\n")
                    elif self.platform == LibraryPlatform.Windows:
                        f.write("$libs = Get-Childitem -Path ./**.lib -Recurse -ErrorAction SilentlyContinue\n")
                        f.write("if ($libs.count -eq 0) {\n")
                        f.write(f"  cmake --build . {extramakeargs} > cemakelog_{lognum}.txt 2>&1\n")
                        f.write("}\n")

                if self.buildconfig.package_install:
                    f.write(
                        "cmake --install . > ceinstall_0.txt 2>&1 || "
                        "{ echo 'cmake --install failed:' >&2; tail -200 ceinstall_0.txt >&2; exit 1; }\n"
                    )
            else:
                if os.path.exists(os.path.join(sourcefolder, "Makefile")):
                    f.write("make clean > cemakeclean.txt 2>&1 || /bin/true\n")
                f.write("rm -f *.so*\n")
                f.write("rm -f *.a\n")
                f.write(self.script_env("CXXFLAGS", cxx_flags))
                f.write(self.script_env("CFLAGS", c_flags))
                logdir = ""
                if self.buildconfig.source_folder:
                    f.write("LOGDIR=$(pwd)/\n")
                    f.write(f"cd {self.buildconfig.source_folder}\n")
                    logdir = "${LOGDIR}"

                if self.buildconfig.build_type == "make":
                    configurepath = os.path.join(sourcefolder, self.buildconfig.source_folder, "configure")
                    if os.path.exists(configurepath):
                        if self.buildconfig.package_install:
                            configure_cmd = f"./configure {configure_flags} --prefix={installfolder}"
                        else:
                            configure_cmd = f"./configure {configure_flags}"
                        configure_log = f"{logdir}ceconfiglog.txt"
                        f.write(
                            f"{configure_cmd} > {configure_log} 2>&1 || "
                            f"{{ echo 'configure failed:' >&2; tail -200 {configure_log} >&2; exit 1; }}\n"
                        )

                for line in self.buildconfig.prebuild_script:
                    f.write(f"{line}\n")

                par_args = []
                if self.platform == LibraryPlatform.Linux:
                    par_args = ["-j$NUMCPUS"]

                extramakeargs = " ".join(
                    par_args
                    + [
                        self.expand_make_arg(arg, compilerTypeOrGcc, buildtype, arch, stdver, stdlib)
                        for arg in self.buildconfig.extra_make_arg
                    ]
                )

                if len(self.buildconfig.make_targets) != 0:
                    for lognum, target in enumerate(self.buildconfig.make_targets):
                        f.write(f"{make_utility} {extramakeargs} {target} > {logdir}cemakelog_{lognum}.txt 2>&1\n")
                else:
                    lognum = 0
                    for lib in itertools.chain(self.buildconfig.staticliblink, self.buildconfig.sharedliblink):
                        f.write(f"{make_utility} {extramakeargs} {lib} > {logdir}cemakelog_{lognum}.txt 2>&1\n")
                        lognum += 1

                    if not self.buildconfig.package_install:
                        if self.platform == LibraryPlatform.Linux:
                            if len(self.buildconfig.staticliblink) != 0:
                                f.write("libsfound=$(find . -iname 'lib*.a')\n")
                            elif len(self.buildconfig.sharedliblink) != 0:
                                f.write("libsfound=$(find . -iname 'lib*.so*')\n")

                            f.write('if [ "$libsfound" = "" ]; then\n')
                            f.write(f"  {make_utility} {extramakeargs} all > {logdir}cemakelog_{lognum}.txt 2>&1\n")
                            f.write("fi\n")
                        elif self.platform == LibraryPlatform.Windows:
                            f.write("$libs = Get-Childitem -Path ./**.lib -Recurse -ErrorAction SilentlyContinue\n")
                            f.write("if ($libs.count -eq 0) {\n")
                            f.write(f"  {make_utility} {extramakeargs} all > {logdir}cemakelog_{lognum}.txt 2>&1\n")
                            f.write("}\n")

                if self.buildconfig.package_install:
                    f.write(f"{make_utility} install > {logdir}ceinstall_0.txt 2>&1\n")

            if not self.buildconfig.package_install:
                for lib in self.buildconfig.staticliblink:
                    f.write(f"find . -iname 'lib{lib}*.a' -type f -exec mv {{}} . \\;\n")

                for lib in self.buildconfig.sharedliblink:
                    f.write(f"find . -iname 'lib{lib}*.so*' -type f,l -exec mv {{}} . \\;\n")

            for line in self.buildconfig.postbuild_script:
                expanded_line = self.expand_build_script_line(
                    line, buildos, buildtype, compilerTypeOrGcc, compiler, compilerexe, libcxx, arch, stdver, extraflags
                )
                f.write(f"{expanded_line}\n")

        if self.buildconfig.lib_type == "cshared":
            self.setCurrentConanBuildParameters(
                buildos, buildtype, "cshared", "cshared", libcxx, arch, stdver, extraflags
            )
        elif self.buildconfig.lib_type == "headeronly":
            self.setCurrentConanBuildParameters(
                buildos, buildtype, "headeronly", "headeronly", libcxx, arch, stdver, extraflags
            )
        else:
            self.setCurrentConanBuildParameters(
                buildos, buildtype, compilerTypeOrGcc, compiler, libcxx, arch, stdver, extraflags
            )

    def setCurrentConanBuildParameters(
        self, buildos, buildtype, compilerTypeOrGcc, compiler, libcxx, arch, stdver, extraflags
    ):
        self.current_buildparameters_obj["os"] = buildos
        self.current_buildparameters_obj["buildtype"] = buildtype
        self.current_buildparameters_obj["compiler"] = compilerTypeOrGcc
        self.current_buildparameters_obj["compiler_version"] = compiler
        self.current_buildparameters_obj["libcxx"] = libcxx
        self.current_buildparameters_obj["arch"] = arch
        self.current_buildparameters_obj["stdver"] = stdver
        self.current_buildparameters_obj["flagcollection"] = extraflags
        self.current_buildparameters_obj["library"] = self.libid
        self.current_buildparameters_obj["library_version"] = self.target_name

        self.current_buildparameters = [
            "-s",
            f"os={buildos}",
            "-s",
            f"build_type={buildtype}",
            "-s",
            f"compiler={compilerTypeOrGcc}",
            "-s",
            f"compiler.version={compiler}",
            "-s",
            f"compiler.libcxx={libcxx}",
            "-s",
            f"arch={arch}",
            "-s",
            f"stdver={stdver}",
            "-s",
            f"flagcollection={extraflags}",
        ]

    def writeconanscript(self, buildfolder):
        conanparamsstr = " ".join(self.current_buildparameters)

        if self.platform == LibraryPlatform.Linux:
            with open_script(Path(buildfolder) / "conanexport.sh") as f:
                f.write("#!/bin/sh\n\n")
                f.write(f"conan export-pkg . {self.libname}/{self.target_name} -f {conanparamsstr}\n")
        elif self.platform == LibraryPlatform.Windows:
            with open_script(Path(buildfolder) / "conanexport.ps1") as f:
                f.write(f"conan export-pkg . {self.libname}/{self.target_name} -f {conanparamsstr}\n")

    def write_conan_file_to(self, f: TextIO) -> None:
        libsum = ",".join(
            f'"{lib}"' for lib in itertools.chain(self.buildconfig.staticliblink, self.buildconfig.sharedliblink)
        )

        f.write("from conans import ConanFile, tools\n")
        f.write(f"class {self.libname}Conan(ConanFile):\n")
        f.write(f'    name = "{self.libname}"\n')
        f.write(f'    version = "{self.target_name}"\n')
        f.write('    settings = "os", "compiler", "build_type", "arch", "stdver", "flagcollection"\n')
        f.write(f'    description = "{self.buildconfig.description}"\n')
        f.write(f'    url = "{self.buildconfig.url}"\n')
        f.write('    license = "None"\n')
        f.write('    author = "None"\n')
        f.write("    topics = None\n")
        f.write("    def package(self):\n")

        if self.buildconfig.package_install:
            f.write('        self.copy("*", src="../install", dst=".", keep_path=True)\n')
        else:
            for copy_line in self.buildconfig.copy_files:
                f.write(f"        {copy_line}\n")

            for lib in self.buildconfig.staticliblink:
                f.write(f'        self.copy("lib{lib}*.a", dst="lib", keep_path=False)\n')

            for lib in self.buildconfig.sharedliblink:
                f.write(f'        self.copy("lib{lib}*.so*", dst="lib", keep_path=False)\n')

            for lib in self.buildconfig.staticliblink:
                f.write(f'        self.copy("{lib}*.lib", dst="lib", keep_path=False)\n')

            for lib in self.buildconfig.sharedliblink:
                f.write(f'        self.copy("{lib}*.dll*", dst="lib", keep_path=False)\n')

        f.write("    def package_info(self):\n")
        f.write(f"        self.cpp_info.libs = [{libsum}]\n")

    def writeconanfile(self, buildfolder):
        conanfile = Path(buildfolder) / "conanfile.py"
        if conanfile.exists():
            conanfile.unlink()
        with (conanfile).open(mode="w", encoding="utf-8") as f:
            self.write_conan_file_to(f)

    def countHeaders(self, buildfolder) -> int:
        headerfiles = []
        headerfiles += glob.glob(str(buildfolder / "**" / "*.h"), recursive=True)
        headerfiles += glob.glob(str(buildfolder / "**" / "*.hpp"), recursive=True)
        return len(headerfiles)

    def countValidLibraryBinaries(self, buildfolder, arch, stdlib, is_msvc: bool):
        filesfound = 0

        if self.buildconfig.lib_type == "cshared":
            for lib in self.buildconfig.sharedliblink:
                if is_msvc:
                    filepath = os.path.join(buildfolder, f"{lib}.dll")
                else:
                    filepath = os.path.join(buildfolder, f"lib{lib}.so")
                bininfo = BinaryInfo(self.logger, buildfolder, filepath, self.platform)
                if "libstdc++.so" not in bininfo.ldd_details and "libc++.so" not in bininfo.ldd_details:
                    if not arch:
                        filesfound += 1
                    elif arch == "x86" and "ELF32" in bininfo.readelf_header_details:
                        filesfound += 1
                    elif arch == "x86_64" and "ELF64" in bininfo.readelf_header_details:
                        filesfound += 1
            return filesfound

        for lib in self.buildconfig.staticliblink:
            if is_msvc:
                filepath = os.path.join(buildfolder, f"{lib}.lib")
            else:
                filepath = os.path.join(buildfolder, f"lib{lib}.a")

            if os.path.exists(filepath):
                bininfo = BinaryInfo(self.logger, buildfolder, filepath, self.platform)
                cxxinfo = bininfo.cxx_info_from_binary()
                if is_msvc:
                    archinfo = bininfo.arch_info_from_binary()
                    if arch == "x86" and archinfo["obj_arch"] == "i386":
                        filesfound += 1
                    elif arch == "x86_64" and archinfo["obj_arch"] == "x86_64":
                        filesfound += 1
                    elif not arch:
                        filesfound += 1
                else:
                    if not stdlib or (stdlib == "libc++" and not cxxinfo["has_maybecxx11abi"]):
                        if not arch:
                            filesfound += 1
                        else:
                            if arch == "x86" and (
                                "ELF32" in bininfo.readelf_header_details
                                or "IMAGE_FILE_MACHINE_I386" in bininfo.readelf_header_details
                            ):
                                filesfound += 1
                            elif arch == "x86_64" and (
                                "ELF64" in bininfo.readelf_header_details
                                or "IMAGE_FILE_MACHINE_AMD64" in bininfo.readelf_header_details
                            ):
                                filesfound += 1

            else:
                self.logger.debug(f"{filepath} not found")

        for lib in self.buildconfig.sharedliblink:
            if self.platform == LibraryPlatform.Windows:
                filepath = os.path.join(buildfolder, f"{lib}.dll")
                if not os.path.exists(filepath):
                    filepath = os.path.join(buildfolder, f"lib{lib}.dll")
            else:
                filepath = os.path.join(buildfolder, f"lib{lib}.so")

            bininfo = BinaryInfo(self.logger, buildfolder, filepath, self.platform)
            if self.platform == LibraryPlatform.Windows:
                archinfo = bininfo.arch_info_from_binary()
                if arch == "x86" and archinfo["obj_arch"] == "i386":
                    filesfound += 1
                elif arch == "x86_64" and archinfo["obj_arch"] == "x86_64":
                    filesfound += 1
                elif not arch:
                    filesfound += 1
            else:
                if (not stdlib and "libstdc++.so" in bininfo.ldd_details) or (
                    stdlib and f"{stdlib}.so" in bininfo.ldd_details
                ):
                    if not arch:
                        filesfound += 1
                    elif arch == "x86" and (
                        "ELF32" in bininfo.readelf_header_details
                        or "IMAGE_FILE_MACHINE_I386" in bininfo.readelf_header_details
                    ):
                        filesfound += 1
                    elif arch == "x86_64" and (
                        "ELF64" in bininfo.readelf_header_details
                        or "IMAGE_FILE_MACHINE_AMD64" in bininfo.readelf_header_details
                    ):
                        filesfound += 1

        return filesfound

    def executeconanscript(self, buildfolder):
        if self.platform == LibraryPlatform.Linux:
            if subprocess.call(["./conanexport.sh"], cwd=buildfolder) == 0:
                self.logger.info("Export succesful")
                return BuildStatus.Ok
            else:
                return BuildStatus.Failed
        elif self.platform == LibraryPlatform.Windows:
            if subprocess.call(["pwsh", "./conanexport.ps1"], cwd=buildfolder) == 0:
                self.logger.info("Export succesful")
                return BuildStatus.Ok
            else:
                return BuildStatus.Failed

    def executebuildscript(self, buildfolder):
        try:
            if self.platform == LibraryPlatform.Linux:
                if subprocess.call(["./" + self.script_filename], cwd=buildfolder, timeout=build_timeout) == 0:
                    self.logger.info(f"Build succeeded in {buildfolder}")
                    return BuildStatus.Ok
                else:
                    self.logger.debug(f"Build failed in {buildfolder}")
                    return BuildStatus.Failed
            elif self.platform == LibraryPlatform.Windows:
                if subprocess.call(["pwsh", "./" + self.script_filename], cwd=buildfolder, timeout=build_timeout) == 0:
                    self.logger.info(f"Build succeeded in {buildfolder}")
                    return BuildStatus.Ok
                else:
                    self.logger.debug(f"Build failed in {buildfolder}")
                    return BuildStatus.Failed

        except subprocess.TimeoutExpired:
            self.logger.info(f"Build timed out and was killed ({buildfolder})")
            return BuildStatus.TimedOut

    def makebuildhash(
        self, compiler, options, toolchain, buildos, buildtype, arch, stdver, stdlib, flagscombination, iteration
    ):
        flagsstr = "|".join(x for x in flagscombination)

        self.logger.info(
            f"Building {self.libname} {self.target_name} for [{compiler},{options},{toolchain},{buildos},{buildtype},{arch},{stdver},{stdlib},{flagsstr}]"
        )

        return compiler + "_" + str(iteration)

    def _get_possible_builds(self) -> PossibleBuilds:
        """Return the conan-server /search response for this (libname, target_name), cached."""
        if self._possible_builds is None:
            self._possible_builds = fetch_possible_builds(
                self.libname,
                self.target_name,
                lambda url: self.resil_get(url, stream=False, timeout=_TIMEOUT),
                self.logger,
            )
        return self._possible_builds

    def get_conan_hash(self, buildfolder: str) -> str | None:
        if self.install_context.dry_run:
            return None
        target = build_target_settings(self.current_buildparameters_obj)
        return find_matching_package_id(self._get_possible_builds(), target)

    def conanproxy_login(self):
        url = f"{conanserver_url}/login"

        login_body = defaultdict(lambda: [])
        if os.environ.get("CONAN_PASSWORD"):
            login_body["password"] = os.environ.get("CONAN_PASSWORD")
        else:
            try:
                login_body["password"] = get_ssm_param("/compiler-explorer/conanpwd")
            except botocore.exceptions.NoCredentialsError as exc:
                raise RuntimeError(
                    "No password found for conan server, setup AWS credentials to access the CE SSM, or set CONAN_PASSWORD environment variable"
                ) from exc

        request = self.resil_post(url, json_data=json.dumps(login_body))
        if not request.ok:
            self.logger.info(request.text)
            raise PostFailure(f"Post failure for {url}: {request}")
        else:
            response = json.loads(request.content)
            self.conanserverproxy_token = response["token"]

    def save_build_logging(self, builtok, buildfolder, extralogtext):
        if builtok == BuildStatus.Failed:
            url = f"{conanserver_url}/buildfailed"
        elif builtok == BuildStatus.Ok:
            url = f"{conanserver_url}/buildsuccess"
        elif builtok == BuildStatus.TimedOut:
            url = f"{conanserver_url}/buildfailed"
        else:
            return

        loggingfiles = []
        loggingfiles += glob.glob(buildfolder + "/" + self.script_filename)
        loggingfiles += glob.glob(buildfolder + "/cecmake*.txt")
        loggingfiles += glob.glob(buildfolder + "/ceconfiglog.txt")
        loggingfiles += glob.glob(buildfolder + "/cemake*.txt")
        loggingfiles += glob.glob(buildfolder + "/ceinstall*.txt")

        logging_data = ""
        for logfile in loggingfiles:
            logging_data += Path(logfile).read_text(encoding="utf-8")

        if builtok == BuildStatus.TimedOut:
            logging_data = logging_data + "\n\n" + "BUILD TIMED OUT!!"

        buildparameters_copy = self.current_buildparameters_obj.copy()
        buildparameters_copy["logging"] = logging_data + "\n\n" + extralogtext
        commit_hash = self.get_commit_hash()
        buildparameters_copy["commithash"] = commit_hash

        if builtok == BuildStatus.Ok:
            self.history.success(self.current_buildparameters_obj, commit_hash)
        elif builtok != BuildStatus.Skipped:
            self.history.failed(self.current_buildparameters_obj, commit_hash)

        headers = {"Content-Type": "application/json", "Authorization": "Bearer " + self.conanserverproxy_token}

        result = self.resil_post(url, json_data=json.dumps(buildparameters_copy), headers=headers)

        # Failed/TimedOut add a failure row server-side; Ok deletes one. Either way the cache is stale.
        self._failed_builds = None

        return result

    def get_build_annotations(self, buildfolder):
        if buildfolder in self._annotations_cache:
            self.logger.debug(f"Using cached annotations for {buildfolder}")
            return self._annotations_cache[buildfolder]

        conanhash = self.get_conan_hash(buildfolder)
        if conanhash is None:
            result = defaultdict(lambda: [])
            self._annotations_cache[buildfolder] = result
            return result

        url = f"{conanserver_url}/annotations/{self.libname}/{self.target_name}/{conanhash}"
        with tempfile.TemporaryFile() as fd:
            request = self.resil_get(url, stream=True, timeout=_TIMEOUT)
            if not request or not request.ok:
                raise FetchFailure(f"Fetch failure for {url}: {request}")
            for chunk in request.iter_content(chunk_size=4 * 1024 * 1024):
                fd.write(chunk)
            fd.flush()
            fd.seek(0)
            buffer = fd.read()
            result = json.loads(buffer)
            self._annotations_cache[buildfolder] = result
            return result

    def get_commit_hash(self) -> str:
        if self.current_commit_hash:
            return self.current_commit_hash

        if os.path.exists(f"{self.sourcefolder}/.git"):
            lastcommitinfo = subprocess.check_output([
                "git",
                "-C",
                self.sourcefolder,
                "log",
                "-1",
                "--oneline",
                "--no-color",
            ]).decode("utf-8", "ignore")
            self.logger.debug(f"last git commit: {lastcommitinfo}")
            match = GITCOMMITHASH_RE.match(lastcommitinfo)
            if match:
                self.current_commit_hash = match[1]
            else:
                self.current_commit_hash = self.target_name
                return self.current_commit_hash
        else:
            self.current_commit_hash = self.target_name

        return self.current_commit_hash

    def _get_failed_builds(self) -> FailedBuilds:
        if self._failed_builds is None:
            self._failed_builds = fetch_failed_builds(
                self.libname,
                self.target_name,
                lambda url: self.resil_get(url, stream=False, timeout=_TIMEOUT),
                self.logger,
            )
        return self._failed_builds

    def has_failed_before(self):
        return match_failed_build(self._get_failed_builds(), self.current_buildparameters_obj, self.get_commit_hash())

    def is_already_uploaded(self, buildfolder):
        annotations = self.get_build_annotations(buildfolder)

        if "commithash" in annotations:
            commithash = self.get_commit_hash()

            return commithash == annotations["commithash"]
        else:
            return False

    def set_as_uploaded(self, buildfolder):
        # We need the conan package_id (a deterministic SHA from compiler+version+libcxx+arch+...)
        # to PUT annotations against /annotations/{lib}/{ver}/{package_id}. get_conan_hash
        # derives the id by querying the server's /search index, which only lists packages
        # already on the server -- so for a freshly built package, we must upload first.
        annotations = self.get_build_annotations(buildfolder)
        if "commithash" not in annotations:
            self.upload_builds()

        conanhash = self.get_conan_hash(buildfolder)
        if conanhash is None:
            raise RuntimeError(f"Error determining conan hash in {buildfolder}")

        self.logger.info(f"conanhash: {conanhash}")
        annotations["commithash"] = self.get_commit_hash()

        for lib in itertools.chain(self.buildconfig.staticliblink, self.buildconfig.sharedliblink):
            lib_filepath = ""
            if os.path.exists(os.path.join(buildfolder, f"lib{lib}.a")):
                lib_filepath = os.path.join(buildfolder, f"lib{lib}.a")
            elif os.path.exists(os.path.join(buildfolder, f"lib{lib}.so")):
                lib_filepath = os.path.join(buildfolder, f"lib{lib}.so")
            elif os.path.exists(os.path.join(buildfolder, f"{lib}.lib")):
                lib_filepath = os.path.join(buildfolder, f"{lib}.lib")

            if lib_filepath:
                bininfo = BinaryInfo(self.logger, buildfolder, lib_filepath, self.platform)
                libinfo = bininfo.cxx_info_from_binary()
                archinfo = bininfo.arch_info_from_binary()
                annotations["cxx11"] = libinfo["has_maybecxx11abi"]
                annotations["machine"] = archinfo["elf_machine"]
                if self.platform == LibraryPlatform.Windows:
                    annotations["osabi"] = archinfo["obj_arch"]
                else:
                    annotations["osabi"] = archinfo["elf_osabi"]

        headers = {"Content-Type": "application/json", "Authorization": "Bearer " + self.conanserverproxy_token}

        url = f"{conanserver_url}/annotations/{self.libname}/{self.target_name}/{conanhash}"
        request = self.resil_post(url, json_data=json.dumps(annotations), headers=headers)
        if not request.ok:
            raise PostFailure(f"Post failure for {url}: {request}")

    def makebuildfor(
        self,
        compiler,
        options,
        exe,
        compiler_type,
        toolchain,
        buildos,
        buildtype,
        arch,
        stdver,
        stdlib,
        flagscombination,
        ld_path,
        staging: StagingDir,
        compiler_props,
        iteration,
    ):
        combined_hash = self.makebuildhash(
            compiler, options, toolchain, buildos, buildtype, arch, stdver, stdlib, flagscombination, iteration
        )

        build_folder = os.path.join(staging.path, combined_hash)
        if os.path.exists(build_folder):
            shutil.rmtree(build_folder, ignore_errors=True)
        os.makedirs(build_folder, exist_ok=True)
        requires_tree_copy = self.buildconfig.build_type != "cmake"

        self.logger.debug(f"Buildfolder: {build_folder}")

        install_folder = os.path.join(staging.path, "install")
        self.logger.debug(f"Installfolder: {install_folder}")

        self.writebuildscript(
            build_folder,
            install_folder,
            self.sourcefolder,
            compiler,
            options,
            exe,
            compiler_type,
            toolchain,
            buildos,
            buildtype,
            arch,
            stdver,
            stdlib,
            flagscombination,
            ld_path,
            compiler_props,
        )
        self.writeconanfile(build_folder)
        extralogtext = ""

        if not self.forcebuild and self.has_failed_before():
            self.logger.info("Build has failed before, not re-attempting")
            return BuildStatus.Skipped

        if self.is_already_uploaded(build_folder):
            self.logger.info("Build already uploaded")
            if not self.forcebuild:
                return BuildStatus.Skipped

        if requires_tree_copy:
            shutil.copytree(self.sourcefolder, build_folder, dirs_exist_ok=True)
            self.writeconanfile(build_folder)

        if not self.install_context.dry_run and not self.conanserverproxy_token:
            self.conanproxy_login()

        build_status = self.executebuildscript(build_folder)
        if build_status == BuildStatus.Ok:
            if self.buildconfig.package_install:
                if self.buildconfig.lib_type == "headeronly":
                    self.logger.debug("Header only library, no binaries to upload")
                    filesfound = self.countHeaders(Path(install_folder) / "include")
                else:
                    filesfound = self.countValidLibraryBinaries(
                        Path(install_folder) / "lib", arch, stdlib, compiler_type == "win32-vc"
                    )
                    filesfound = filesfound + self.countValidLibraryBinaries(
                        Path(install_folder) / "bin", arch, stdlib, compiler_type == "win32-vc"
                    )
            else:
                filesfound = self.countValidLibraryBinaries(build_folder, arch, stdlib, compiler_type == "win32-vc")

            if filesfound != 0:
                self.writeconanscript(build_folder)
                if not self.install_context.dry_run:
                    build_status = self.executeconanscript(build_folder)
                    if build_status == BuildStatus.Ok:
                        self.needs_uploading += 1
                        self.set_as_uploaded(build_folder)
            else:
                extralogtext = "No binaries found to export"
                self.logger.info(extralogtext)
                build_status = BuildStatus.Failed

        if not self.install_context.dry_run:
            self.save_build_logging(build_status, build_folder, extralogtext)

        if build_status == BuildStatus.Ok:
            if self.buildconfig.build_type == "cmake":
                self.build_cleanup(build_folder)
            elif self.buildconfig.build_type == "make":
                subprocess.call(["make", "clean"], cwd=build_folder)

        return build_status

    def build_cleanup(self, buildfolder):
        if self.install_context.dry_run:
            self.logger.info(f"Would remove directory {buildfolder} but in dry-run mode")
        else:
            shutil.rmtree(buildfolder, ignore_errors=True)
            self.logger.info(f"Removing {buildfolder}")

    def upload_builds(self):
        if self.needs_uploading > 0:
            if not self.install_context.dry_run:
                self.logger.info("Uploading cached builds")
                subprocess.check_call([
                    "conan",
                    "upload",
                    f"{self.libname}/{self.target_name}",
                    "--all",
                    "-r=ceserver",
                    "-c",
                ])
                self.logger.debug("Clearing cache to speed up next upload")
                subprocess.check_call(["conan", "remove", "-f", f"{self.libname}/{self.target_name}"])
            self.needs_uploading = 0
            # Force re-fetch on next get_conan_hash so post-upload set_as_uploaded sees the new package.
            self._possible_builds = None

    def get_compiler_type(self, compiler):
        compilerType = ""
        if "compilerType" in self.compilerprops[compiler]:
            compilerType = self.compilerprops[compiler]["compilerType"]
        else:
            raise RuntimeError(f"Something is wrong with {compiler}")

        if self.compilerprops[compiler]["compilerType"] == "clang-intel":
            # hack for icpx so we don't get duplicate builds
            compilerType = "gcc"

        return compilerType

    def download_compiler_usage_csv(self):
        url = "https://compiler-explorer.s3.amazonaws.com/public/compiler_usage.csv"
        with tempfile.TemporaryFile() as fd:
            request = self.resil_get(url, stream=True, timeout=_TIMEOUT)
            if not request or not request.ok:
                raise FetchFailure(f"Fetch failure for {url}: {request}")
            for chunk in request.iter_content(chunk_size=4 * 1024 * 1024):
                fd.write(chunk)
            fd.flush()
            fd.seek(0)

            reader = csv.DictReader(line.decode("utf-8") for line in fd.readlines())
            for row in reader:
                popular_compilers[row["compiler"]] = int(row["times_used"])

    def is_popular_enough(self, compiler):
        if len(popular_compilers) == 0:
            self.logger.debug("downloading compiler popularity csv")
            self.download_compiler_usage_csv()

        if compiler not in popular_compilers:
            return False

        if popular_compilers[compiler] < compiler_popularity_treshhold:
            return False

        return True

    def should_build_with_compiler(self, compiler, checkcompiler, buildfor):
        if checkcompiler and compiler != checkcompiler:
            return False

        if compiler in self.buildconfig.skip_compilers:
            return False

        compilerType = self.get_compiler_type(compiler)

        exe = self.compilerprops[compiler]["exe"]

        if buildfor == "allclang" and compilerType != "clang":
            return False
        elif buildfor == "allicc" and "/icc" not in exe:
            return False
        elif buildfor == "allgcc" and compilerType:
            return False

        if self.check_compiler_popularity and self.buildconfig.lib_type != "headeronly":
            if not self.is_popular_enough(compiler):
                self.logger.info(f"compiler {compiler} is not popular enough")
                return False

        return True

    def makebuild(self, buildfor):
        builds_failed = 0
        builds_succeeded = 0
        builds_skipped = 0
        checkcompiler = ""

        build_supported_os = [self.platform.value]
        build_supported_buildtype = ["Debug"]
        build_supported_arch = ["x86_64", "x86"]
        build_supported_stdver = [""]
        build_supported_stdlib = ["", "libc++"]
        build_supported_flagscollection = [[""]]

        if buildfor:
            self.forcebuild = True

        if self.buildconfig.lib_type == "cshared":
            checkcompiler = self.buildconfig.use_compiler
            if checkcompiler not in self.compilerprops:
                self.logger.error(
                    f"Unknown compiler {checkcompiler} to build cshared lib {self.buildconfig.sharedliblink}"
                )
        elif self.buildconfig.lib_type == "headeronly":
            if self.platform == LibraryPlatform.Windows:
                checkcompiler = "mingw64_ucrt_gcc_1220"
                self.logger.info(
                    f"Header-only library, but running on Windows, so attempting build with {checkcompiler}"
                )
                if checkcompiler not in self.compilerprops:
                    self.logger.error(f"Unknown compiler {checkcompiler}")
                build_supported_arch = [""]
            else:
                self.logger.info("Header-only library, no need to build")
                return [builds_succeeded, 1, builds_failed]
        elif buildfor == "nonx86":
            self.forcebuild = True
            checkcompiler = ""
        elif buildfor == "onlyx86":
            self.forcebuild = True
            checkcompiler = ""
            build_supported_arch = ["x86"]
        elif buildfor == "allclang" or buildfor == "allicc" or buildfor == "allgcc" or buildfor == "forceall":
            self.forcebuild = True
            checkcompiler = ""
        elif buildfor:
            checkcompiler = buildfor
            if checkcompiler not in self.compilerprops:
                self.logger.error(f"Unknown compiler {checkcompiler}")

        for compiler in self.compilerprops:
            if compiler in disable_compiler_ids:
                self.logger.debug(f"Skipping {compiler}")
                continue

            if not self.should_build_with_compiler(compiler, checkcompiler, buildfor):
                self.logger.debug(f"Skipping {compiler}")
                continue

            compilerType = self.get_compiler_type(compiler)
            is_msvc = compilerType == "win32-vc"

            exe = self.compilerprops[compiler]["exe"]

            options = self.compilerprops[compiler]["options"]

            toolchain = self.getToolchainPathFromOptions(options)
            fixedStdver = self.getStdVerFromOptions(options)
            fixedStdlib = self.getStdLibFromOptions(options)

            if not toolchain:
                toolchain = str(os.path.abspath(Path(exe).parent / ".."))

            if (
                self.buildconfig.build_fixed_stdlib
                and fixedStdlib
                and self.buildconfig.build_fixed_stdlib != fixedStdlib
            ):
                continue

            stdlibs = [""]
            if self.buildconfig.lib_type != "cshared":
                if compiler in disable_clang_libcpp:
                    stdlibs = [""]
                elif fixedStdlib:
                    self.logger.debug(f"Fixed stdlib {fixedStdlib}")
                    stdlibs = [fixedStdlib]
                else:
                    if self.buildconfig.build_fixed_stdlib:
                        if self.buildconfig.build_fixed_stdlib != "libstdc++":
                            stdlibs = [self.buildconfig.build_fixed_stdlib]
                    else:
                        if not compilerType:
                            self.logger.debug("Gcc-like compiler")
                        elif compilerType == "clang":
                            self.logger.debug("Clang-like compiler")
                            stdlibs = build_supported_stdlib
                        else:
                            self.logger.debug("Some other compiler")

            archs = build_supported_arch

            if compiler in disable_clang_32bit:
                archs = ["x86_64"]
            else:
                if self.buildconfig.build_fixed_arch:
                    if not self.does_compiler_support(
                        exe,
                        compilerType,
                        self.buildconfig.build_fixed_arch,
                        self.compilerprops[compiler]["options"],
                        self.compilerprops[compiler]["ldPath"],
                    ):
                        self.logger.debug(
                            f"Compiler {compiler} does not support fixed arch {self.buildconfig.build_fixed_arch}"
                        )
                        continue
                    else:
                        archs = [self.buildconfig.build_fixed_arch]

                if is_msvc:
                    # msvc can only do 1 architecture, so no need to try things it doesn't support
                    if self.does_compiler_support_x86(
                        exe,
                        compilerType,
                        self.compilerprops[compiler]["options"],
                        self.compilerprops[compiler]["ldPath"],
                    ):
                        archs = ["x86"]
                    elif self.does_compiler_support_amd64(
                        exe,
                        compilerType,
                        self.compilerprops[compiler]["options"],
                        self.compilerprops[compiler]["ldPath"],
                    ):
                        archs = ["x86_64"]

                        if buildfor == "onlyx86":
                            archs = ["x86"]
                    else:
                        archs = [""]
                else:
                    if not self.does_compiler_support_x86(
                        exe,
                        compilerType,
                        self.compilerprops[compiler]["options"],
                        self.compilerprops[compiler]["ldPath"],
                    ):
                        if self.does_compiler_support_amd64(
                            exe,
                            compilerType,
                            self.compilerprops[compiler]["options"],
                            self.compilerprops[compiler]["ldPath"],
                        ):
                            archs = ["x86_64"]

                            if buildfor == "onlyx86":
                                archs = ["x86"]
                        else:
                            archs = [""]

            if buildfor == "nonx86" and archs[0]:
                continue
            if buildfor == "onlyx86" and not archs[0]:
                continue

            stdvers = build_supported_stdver
            if fixedStdver:
                stdvers = [fixedStdver]

            # Use Release build type for MSVC compilers on Windows
            buildtypes = build_supported_buildtype
            if is_msvc and self.platform == LibraryPlatform.Windows:
                buildtypes = ["Release"]

            iteration = 0
            for args in itertools.product(
                build_supported_os, buildtypes, archs, stdvers, stdlibs, build_supported_flagscollection
            ):
                iteration += 1
                try:
                    with self.install_context.new_staging_dir() as staging:
                        buildstatus = self.makebuildfor(
                            compiler,
                            options,
                            exe,
                            compilerType,
                            toolchain,
                            *args,
                            self.compilerprops[compiler]["ldPath"],
                            staging,
                            self.compilerprops[compiler],
                            iteration,
                        )
                        if buildstatus == BuildStatus.Ok:
                            builds_succeeded = builds_succeeded + 1
                        elif buildstatus == BuildStatus.Skipped:
                            builds_skipped = builds_skipped + 1
                        else:
                            builds_failed = builds_failed + 1
                except Exception:
                    # Broad catch is intentional: one bad combination (e.g. conan rejecting a setting)
                    # must not abort the rest of the batch.
                    self.logger.exception(f"Build of {compiler} {args} failed with an unexpected exception")
                    builds_failed = builds_failed + 1

            if builds_succeeded > 0:
                self.upload_builds()

        return [builds_succeeded, builds_skipped, builds_failed]
