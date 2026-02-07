"""Go library builder for Compiler Explorer.

This module builds Go modules for specific compiler versions, capturing only
the GOCACHE delta (new files) to avoid duplicating the stdlib cache.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
from collections import defaultdict
from collections.abc import Generator
from enum import Enum, unique
from pathlib import Path
from typing import Any, TextIO

import requests
from urllib3.exceptions import ProtocolError

from lib.amazon import get_ssm_param
from lib.amazon_properties import get_properties_compilers_and_libraries
from lib.cache_delta import CacheDeltaCapture
from lib.installation_context import InstallationContext, PostFailure
from lib.library_build_config import LibraryBuildConfig
from lib.library_platform import LibraryPlatform
from lib.staging import StagingDir

_LOGGER = logging.getLogger(__name__)

_TIMEOUT = 600
BUILD_TIMEOUT = 600

# Compilers to skip (nightly/unstable versions and gccgo which doesn't support modules)
SKIP_COMPILERS = ["gotip", "go-tip", "gccgo"]

# Compiler type prefixes for Conan classification
GCCGO_PREFIXES = ["gccgo"]


def get_compiler_type(compiler_id: str) -> str:
    """Determine Conan compiler type from compiler ID.

    Returns 'gccgo' for gccgo compilers, 'golang' for standard Go toolchain.
    """
    for prefix in GCCGO_PREFIXES:
        if compiler_id.startswith(prefix):
            return "gccgo"
    return "golang"


def get_build_method(compiler_id: str) -> str:
    """Determine build method from compiler ID.

    Returns 'gccgo' for gccgo compilers, 'gomod' for standard Go toolchain.
    """
    for prefix in GCCGO_PREFIXES:
        if compiler_id.startswith(prefix):
            return "gccgo"
    return "gomod"


# Build configuration
BUILD_SUPPORTED_OS = ["Linux"]
BUILD_SUPPORTED_BUILDTYPE = ["Debug"]
BUILD_SUPPORTED_ARCH = ["x86_64"]

# Conan server URL
CONANSERVER_URL = "https://conan.compiler-explorer.com"

# Cache for compiler properties
_propsandlibs: dict[str, Any] = defaultdict(lambda: [])

CONANINFOHASH_RE = re.compile(r"\s+ID:\s(\w*)")


def clear_properties_cache() -> None:
    """Clear the compiler properties cache. Used for testing."""
    _propsandlibs.clear()


@unique
class BuildStatus(Enum):
    Ok = 0
    Failed = 1
    Skipped = 2
    TimedOut = 3


@contextlib.contextmanager
def open_script(script: Path) -> Generator[TextIO, None, None]:
    """Context manager to create an executable script file."""
    with script.open("w", encoding="utf-8") as f:
        yield f
    script.chmod(0o755)


class GoLibraryBuilder:
    """Builds Go modules for specific compiler versions.

    This builder:
    1. Downloads module sources to a GOPATH
    2. Builds with the compiler's stdlib cache as baseline
    3. Captures only the GOCACHE delta (new compiled artifacts)
    4. Packages both cache_delta and module_sources for Conan
    """

    def __init__(
        self,
        logger: logging.Logger,
        language: str,
        libname: str,
        target_name: str,
        install_context: InstallationContext,
        buildconfig: LibraryBuildConfig,
    ):
        self.logger = logger
        self.language = language
        self.libname = libname
        self.buildconfig = buildconfig
        self.install_context = install_context
        self.target_name = target_name
        self.forcebuild = False
        self.current_buildparameters_obj: dict[str, Any] = defaultdict(lambda: [])
        self.current_buildparameters: list[str] = []
        self.needs_uploading = 0
        # Prefix with 'go_' to avoid Conan namespace collisions with other languages
        self.libid = f"go_{self.libname}"
        self.conanserverproxy_token: str | None = None
        self._conan_hash_cache: dict[str, str | None] = {}
        self._annotations_cache: dict[str, dict] = {}
        self.http_session = requests.Session()

        # Get module path from buildconfig
        self.module_path = buildconfig.config_get("module", "")
        if not self.module_path:
            raise RuntimeError(f"Missing 'module' config for Go library {libname}")

        # Import path - used for modules where root package isn't importable (e.g., protobuf)
        # Falls back to module_path if not specified
        self.import_path = buildconfig.config_get("import_path", self.module_path)

        # Load compiler properties
        if self.language in _propsandlibs:
            self.compilerprops, self.libraryprops = _propsandlibs[self.language]
        else:
            self.compilerprops, self.libraryprops = get_properties_compilers_and_libraries(
                self.language, self.logger, LibraryPlatform.Linux, True
            )
            _propsandlibs[self.language] = [self.compilerprops, self.libraryprops]

        self._complete_build_config()

    def _complete_build_config(self) -> None:
        """Fill in build config from library properties."""
        if self.libid in self.libraryprops:
            lib_props = self.libraryprops[self.libid]
            if "description" in lib_props:
                self.buildconfig.description = lib_props["description"]
            if "name" in lib_props:
                self.buildconfig.description = lib_props["name"]
            if "url" in lib_props:
                self.buildconfig.url = lib_props["url"]

    def _get_go_binary(self, compiler: str) -> Path:
        """Get path to Go binary for a compiler."""
        exe = self.compilerprops[compiler].get("exe", "")
        if not exe:
            raise RuntimeError(f"No exe found for compiler {compiler}")
        return Path(exe)

    def _get_goroot(self, compiler: str) -> Path:
        """Get GOROOT for a compiler."""
        exe = self._get_go_binary(compiler)
        # Go binary is at GOROOT/bin/go, so GOROOT is two levels up
        return exe.parent.parent

    def _get_stdlib_cache(self, compiler: str) -> Path | None:
        """Get path to stdlib cache for a compiler."""
        goroot = self._get_goroot(compiler)
        # Check both possible locations (as in golang.ts)
        cache_path = goroot.parent / "cache"
        if cache_path.exists():
            return cache_path
        cache_path = goroot / "cache"
        if cache_path.exists():
            return cache_path
        return None

    def _download_module(self, go_binary: Path, gopath: Path, goroot: Path) -> bool:
        """Download module sources to GOPATH."""
        module_spec = f"{self.module_path}@{self.target_name}"
        self.logger.info("Downloading module %s", module_spec)

        env = os.environ.copy()
        env["GOROOT"] = str(goroot)
        env["GOPATH"] = str(gopath)
        env["GOPROXY"] = "https://proxy.golang.org,direct"

        try:
            result = subprocess.run(
                [str(go_binary), "mod", "download", module_spec],
                env=env,
                capture_output=True,
                text=True,
                timeout=_TIMEOUT,
                check=False,
            )
            if result.returncode != 0:
                self.logger.error("Failed to download module: %s", result.stderr)
                return False
            return True
        except subprocess.TimeoutExpired:
            self.logger.error("Timeout downloading module %s", module_spec)
            return False

    def _build_module(
        self,
        go_binary: Path,
        goroot: Path,
        gopath: Path,
        gocache: Path,
        build_dir: Path,
    ) -> bool:
        """Build the module to populate GOCACHE."""
        self.logger.info("Building module to populate cache")

        # Create a minimal test program that imports the module
        # Use import_path for modules where root package isn't importable (e.g., protobuf)
        test_program = build_dir / "main.go"
        test_program.write_text(f'''package main

import _ "{self.import_path}"

func main() {{}}
''')

        go_mod = build_dir / "go.mod"
        go_mod.write_text(f"""module testbuild

go 1.21

require {self.module_path} {self.target_name}
""")

        env = os.environ.copy()
        env["GOROOT"] = str(goroot)
        env["GOPATH"] = str(gopath)
        env["GOCACHE"] = str(gocache)
        env["GOPROXY"] = "https://proxy.golang.org,direct"

        # Run go mod tidy to get go.sum
        subprocess.run(
            [str(go_binary), "mod", "tidy"],
            env=env,
            cwd=build_dir,
            capture_output=True,
            timeout=_TIMEOUT,
            check=False,
        )

        # Build to compile the module
        try:
            result = subprocess.run(
                [str(go_binary), "build", "-v", "-o", "/dev/null", "."],
                env=env,
                cwd=build_dir,
                capture_output=True,
                text=True,
                timeout=BUILD_TIMEOUT,
                check=False,
            )
            if result.returncode != 0:
                self.logger.error("Build failed: %s", result.stderr)
                return False
            return True
        except subprocess.TimeoutExpired:
            self.logger.error("Build timed out")
            return False

    def _get_go_sum(self, build_dir: Path) -> str:
        """Get go.sum content after build."""
        go_sum_path = build_dir / "go.sum"
        if go_sum_path.exists():
            return go_sum_path.read_text()
        return ""

    def makebuildhash(
        self,
        compiler: str,
        buildos: str,
        buildtype: str,
        arch: str,
    ) -> str:
        """Create a unique hash for this build configuration."""
        hasher = hashlib.sha256()
        hasher.update(f"{compiler},{buildos},{buildtype},{arch}".encode())
        self.logger.info(
            "Building %s %s for [%s,%s,%s,%s]",
            self.libname,
            self.target_name,
            compiler,
            buildos,
            buildtype,
            arch,
        )
        return f"{compiler}_{hasher.hexdigest()[:16]}"

    def set_current_conan_build_parameters(
        self,
        buildos: str,
        buildtype: str,
        compiler: str,
        arch: str,
    ) -> None:
        """Set Conan build parameters for current build."""
        compiler_type = get_compiler_type(compiler)
        self.current_buildparameters_obj["os"] = buildos
        self.current_buildparameters_obj["buildtype"] = buildtype
        self.current_buildparameters_obj["compiler"] = compiler_type
        self.current_buildparameters_obj["compiler_version"] = compiler
        self.current_buildparameters_obj["libcxx"] = ""
        self.current_buildparameters_obj["arch"] = arch
        self.current_buildparameters_obj["stdver"] = ""
        self.current_buildparameters_obj["flagcollection"] = ""
        self.current_buildparameters_obj["library"] = self.libid
        self.current_buildparameters_obj["library_version"] = self.target_name

        self.current_buildparameters = [
            "-s",
            f"os={buildos}",
            "-s",
            f"build_type={buildtype}",
            "-s",
            f"compiler={compiler_type}",
            "-s",
            f"compiler.version={compiler}",
            "-s",
            "compiler.libcxx=",
            "-s",
            f"arch={arch}",
            "-s",
            "stdver=",
            "-s",
            "flagcollection=",
        ]

    def writeconanscript(self, buildfolder: Path) -> None:
        """Write Conan export script."""
        conanparamsstr = " ".join(self.current_buildparameters)
        with open_script(buildfolder / "conanexport.sh") as f:
            f.write("#!/bin/sh\n\n")
            f.write(f"conan export-pkg . {self.libid}/{self.target_name} -f {conanparamsstr}\n")

    def writeconanfile(self, buildfolder: Path) -> None:
        """Write Conan package file."""
        underscoredlibid = self.libid.replace("-", "_").replace("/", "_").replace(".", "_")
        with (buildfolder / "conanfile.py").open(mode="w", encoding="utf-8") as f:
            f.write("from conans import ConanFile\n")
            f.write(f"class {underscoredlibid}Conan(ConanFile):\n")
            f.write(f'    name = "{self.libid}"\n')
            f.write(f'    version = "{self.target_name}"\n')
            f.write('    settings = "os", "compiler", "build_type", "arch", "stdver", "flagcollection"\n')
            f.write(f'    description = "{self.buildconfig.description}"\n')
            f.write(f'    url = "{self.buildconfig.url}"\n')
            f.write('    license = "None"\n')
            f.write('    author = "None"\n')
            f.write("    topics = None\n")
            f.write("    def package(self):\n")
            f.write('        self.copy("cache_delta/*", dst=".", keep_path=True)\n')
            f.write('        self.copy("module_sources/*", dst=".", keep_path=True)\n')
            f.write('        self.copy("metadata.json", dst=".", keep_path=False)\n')

    def get_conan_hash(self, buildfolder: Path) -> str | None:
        """Query Conan for package hash."""
        if str(buildfolder) in self._conan_hash_cache:
            return self._conan_hash_cache[str(buildfolder)]

        if not self.install_context.dry_run:
            try:
                conaninfo = subprocess.check_output(
                    ["conan", "info", "-r", "ceserver", "."] + self.current_buildparameters,
                    cwd=buildfolder,
                    timeout=_TIMEOUT,
                ).decode("utf-8", "ignore")
                match = CONANINFOHASH_RE.search(conaninfo)
                if match:
                    result = match[1]
                    self._conan_hash_cache[str(buildfolder)] = result
                    return result
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
                self.logger.debug("Conan info failed: %s", e)

        self._conan_hash_cache[str(buildfolder)] = None
        return None

    def resil_post(self, url: str, json_data: str, headers: dict | None = None) -> requests.Response | dict:
        """Resilient POST request with retries."""
        request = None
        retries = 3
        last_error: str | Exception = ""
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
                retries -= 1

        if request is None:
            return {"ok": False, "text": str(last_error)}
        return request

    def conanproxy_login(self) -> None:
        """Login to Conan proxy server."""
        url = f"{CONANSERVER_URL}/login"
        login_body: dict[str, Any] = defaultdict(lambda: [])
        login_body["password"] = get_ssm_param("/compiler-explorer/conanpwd")
        req_data = json.dumps(login_body)

        request = self.resil_post(url, req_data)
        if isinstance(request, dict) or not request.ok:
            error_text = request.get("text", "") if isinstance(request, dict) else request.text
            raise RuntimeError(f"Conan login failed: {error_text}")

        response = json.loads(request.content)
        self.conanserverproxy_token = response["token"]

    def save_build_logging(self, builtok: BuildStatus, logfolder: Path, build_method: str) -> None:
        """Save build status to Conan server."""
        if builtok == BuildStatus.Failed:
            url = f"{CONANSERVER_URL}/buildfailed"
        elif builtok == BuildStatus.Ok:
            url = f"{CONANSERVER_URL}/buildsuccess"
        elif builtok == BuildStatus.TimedOut:
            url = f"{CONANSERVER_URL}/buildfailed"
        else:
            return

        # Read build log if exists
        logging_data = ""
        log_file = logfolder / "buildlog.txt"
        if log_file.exists():
            logging_data = log_file.read_text()

        if builtok == BuildStatus.TimedOut:
            logging_data += "\n\nBUILD TIMED OUT!!"

        buildparameters_copy = dict(self.current_buildparameters_obj)
        buildparameters_copy["logging"] = logging_data
        buildparameters_copy["commithash"] = self.target_name

        if builtok != BuildStatus.Ok:
            buildparameters_copy["flagcollection"] = build_method

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.conanserverproxy_token}",
        }

        req_data = json.dumps(buildparameters_copy)
        request = self.resil_post(url, req_data, headers)
        if isinstance(request, dict) or not request.ok:
            error_text = request.get("text", "") if isinstance(request, dict) else request.text
            raise PostFailure(f"Post failure for {url}: {error_text}")

    def has_failed_before(self, build_method: str) -> bool:
        """Check if this build has failed before."""
        url = f"{CONANSERVER_URL}/hasfailedbefore"
        data = dict(self.current_buildparameters_obj)
        data["flagcollection"] = build_method

        request = self.resil_post(url, json.dumps(data))
        if isinstance(request, dict) or not request.ok:
            return False

        response = json.loads(request.content)
        return response.get("response", False)

    def get_build_annotations(self, buildfolder: Path) -> dict:
        """Get build annotations from Conan server."""
        if str(buildfolder) in self._annotations_cache:
            return self._annotations_cache[str(buildfolder)]

        conanhash = self.get_conan_hash(buildfolder)
        if conanhash is None:
            result: dict = defaultdict(lambda: [])
            self._annotations_cache[str(buildfolder)] = result
            return result

        url = f"{CONANSERVER_URL}/annotations/{self.libid}/{self.target_name}/{conanhash}"
        try:
            request = self.http_session.get(url, timeout=_TIMEOUT)
            if request.ok:
                result = json.loads(request.content)
                self._annotations_cache[str(buildfolder)] = result
                return result
        except (requests.RequestException, json.JSONDecodeError) as e:
            self.logger.debug("Failed to get annotations: %s", e)

        result = defaultdict(lambda: [])
        self._annotations_cache[str(buildfolder)] = result
        return result

    def is_already_uploaded(self, buildfolder: Path) -> bool:
        """Check if this build was already uploaded."""
        annotations = self.get_build_annotations(buildfolder)
        if "commithash" in annotations:
            return self.target_name == annotations["commithash"]
        return False

    def set_as_uploaded(self, buildfolder: Path, build_method: str) -> None:
        """Mark build as uploaded in Conan server."""
        conanhash = self.get_conan_hash(buildfolder)
        if conanhash is None:
            raise RuntimeError(f"Error determining conan hash in {buildfolder}")

        self.logger.info("conanhash: %s", conanhash)

        annotations = self.get_build_annotations(buildfolder)
        if "commithash" not in annotations:
            self.upload_builds()
        annotations["commithash"] = self.target_name
        annotations["build_method"] = build_method

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.conanserverproxy_token}",
        }
        url = f"{CONANSERVER_URL}/annotations/{self.libid}/{self.target_name}/{conanhash}"

        request = self.resil_post(url, json.dumps(annotations), headers)
        if isinstance(request, dict) or not request.ok:
            error_text = request.get("text", "") if isinstance(request, dict) else request.text
            raise RuntimeError(f"Post failure for {url}: {error_text}")

    def executeconanscript(self, buildfolder: Path) -> BuildStatus:
        """Execute Conan export script."""
        try:
            if subprocess.call(["./conanexport.sh"], cwd=buildfolder, timeout=BUILD_TIMEOUT) == 0:
                self.logger.info("Export successful")
                return BuildStatus.Ok
            return BuildStatus.Failed
        except subprocess.TimeoutExpired:
            return BuildStatus.TimedOut

    def upload_builds(self) -> None:
        """Upload cached builds to Conan server."""
        if self.needs_uploading > 0:
            if not self.install_context.dry_run:
                self.logger.info("Uploading cached builds")
                subprocess.check_call([
                    "conan",
                    "upload",
                    f"{self.libid}/{self.target_name}",
                    "--all",
                    "-r=ceserver",
                    "-c",
                ])
                self.logger.debug("Clearing cache to speed up next upload")
                subprocess.check_call(["conan", "remove", "-f", f"{self.libid}/{self.target_name}"])
            self.needs_uploading = 0

    def build_cleanup(self, buildfolder: Path) -> None:
        """Clean up build folder."""
        if self.install_context.dry_run:
            self.logger.info("Would remove directory %s but in dry-run mode", buildfolder)
        else:
            shutil.rmtree(buildfolder, ignore_errors=True)
            self.logger.info("Removing %s", buildfolder)

    def makebuildfor(
        self,
        compiler: str,
        buildos: str,
        buildtype: str,
        arch: str,
        staging: StagingDir,
    ) -> BuildStatus:
        """Build library for a specific compiler configuration."""
        build_method = get_build_method(compiler)

        combined_hash = self.makebuildhash(compiler, buildos, buildtype, arch)
        build_folder = staging.path / combined_hash
        build_folder.mkdir(parents=True, exist_ok=True)

        log_folder = build_folder / "log"
        log_folder.mkdir(exist_ok=True)

        # Set Conan parameters
        self.set_current_conan_build_parameters(buildos, buildtype, compiler, arch)
        self.writeconanfile(build_folder)

        # Check if already built
        if not self.forcebuild and self.has_failed_before(build_method):
            self.logger.info("Build has failed before, not re-attempting")
            return BuildStatus.Skipped

        if self.is_already_uploaded(build_folder):
            self.logger.info("Build already uploaded")
            if not self.forcebuild:
                return BuildStatus.Skipped

        # Get compiler paths
        go_binary = self._get_go_binary(compiler)
        goroot = self._get_goroot(compiler)
        stdlib_cache = self._get_stdlib_cache(compiler)

        if stdlib_cache is None:
            self.logger.warning("No stdlib cache found for %s, building may be slower", compiler)

        # Set up directories
        gopath = build_folder / "gopath"
        gocache = build_folder / "gocache"
        source_dir = build_folder / "source"
        gopath.mkdir(exist_ok=True)
        gocache.mkdir(exist_ok=True)
        source_dir.mkdir(exist_ok=True)

        # Download module
        if not self._download_module(go_binary, gopath, goroot):
            self.save_build_logging(BuildStatus.Failed, log_folder, build_method)
            return BuildStatus.Failed

        # Set up delta capture
        delta_capture = CacheDeltaCapture(gocache)

        # Copy stdlib cache to gocache and capture baseline
        if stdlib_cache and stdlib_cache.exists():
            shutil.copytree(stdlib_cache, gocache, dirs_exist_ok=True)
        delta_capture.capture_baseline()

        # Build module
        if not self._build_module(go_binary, goroot, gopath, gocache, source_dir):
            self.save_build_logging(BuildStatus.Failed, log_folder, build_method)
            return BuildStatus.Failed

        # Capture delta
        delta_count = delta_capture.get_delta_count()
        self.logger.info("Cache delta: %d files", delta_count)

        # Create package structure
        pkg_dir = build_folder / "package"
        pkg_dir.mkdir(exist_ok=True)

        # Copy delta to package
        cache_delta_dir = pkg_dir / "cache_delta"
        delta_capture.copy_delta_to(cache_delta_dir)

        # Copy module sources
        module_sources_dir = pkg_dir / "module_sources"
        mod_cache = gopath / "pkg" / "mod"
        if mod_cache.exists():
            shutil.copytree(mod_cache, module_sources_dir, dirs_exist_ok=True)

        # Create metadata
        go_sum = self._get_go_sum(source_dir)
        metadata = {
            "module": self.module_path,
            "version": self.target_name,
            "go_version": compiler,
            "cache_files_count": delta_count,
            "cache_size_bytes": delta_capture.get_delta_size_bytes(),
            "go_mod_require": f"{self.module_path} {self.target_name}",
            "go_sum": go_sum,
        }
        (pkg_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))

        # Copy package contents to build folder for Conan
        shutil.copytree(pkg_dir, build_folder, dirs_exist_ok=True)

        # Login to Conan if needed
        if not self.install_context.dry_run and not self.conanserverproxy_token:
            self.conanproxy_login()

        # Export to Conan
        self.writeconanscript(build_folder)
        if not self.install_context.dry_run:
            export_status = self.executeconanscript(build_folder)
            if export_status == BuildStatus.Ok:
                self.needs_uploading += 1
                self.set_as_uploaded(build_folder, build_method)
            self.save_build_logging(export_status, log_folder, build_method)

            if export_status != BuildStatus.Ok:
                return export_status
        else:
            self.logger.info("Dry run: would export package")

        self.build_cleanup(build_folder)
        return BuildStatus.Ok

    def makebuild(self, buildfor: str) -> list[int]:
        """Build library for all or specific compiler.

        Args:
            buildfor: Specific compiler ID, "forceall" for all compilers, or empty for all.

        Returns:
            List of [succeeded, skipped, failed] counts.
        """
        builds_failed = 0
        builds_succeeded = 0
        builds_skipped = 0

        if buildfor:
            self.forcebuild = True

        if buildfor == "forceall":
            self.forcebuild = True
            checkcompiler = ""
        else:
            checkcompiler = buildfor
            if checkcompiler and checkcompiler not in self.compilerprops:
                self.logger.error("Unknown compiler %s", checkcompiler)
                return [0, 0, 1]

        with self.install_context.new_staging_dir() as staging:
            for compiler in self.compilerprops:
                if checkcompiler and compiler != checkcompiler:
                    continue

                if compiler in self.buildconfig.skip_compilers:
                    self.logger.debug("Skipping %s (in skip_compilers)", compiler)
                    continue

                if any(skip in compiler for skip in SKIP_COMPILERS):
                    self.logger.debug("Skipping %s (unstable)", compiler)
                    continue

                # Check compiler has exe
                if "exe" not in self.compilerprops[compiler]:
                    self.logger.debug("Skipping %s (no exe)", compiler)
                    continue

                for buildos in BUILD_SUPPORTED_OS:
                    for buildtype in BUILD_SUPPORTED_BUILDTYPE:
                        for arch in BUILD_SUPPORTED_ARCH:
                            buildstatus = self.makebuildfor(compiler, buildos, buildtype, arch, staging)
                            if buildstatus == BuildStatus.Ok:
                                builds_succeeded += 1
                            elif buildstatus == BuildStatus.Skipped:
                                builds_skipped += 1
                            else:
                                builds_failed += 1

                if builds_succeeded > 0:
                    self.upload_builds()

        return [builds_succeeded, builds_skipped, builds_failed]
