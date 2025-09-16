from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from abc import ABC, abstractmethod
from collections import defaultdict
from enum import Enum, unique
from logging import Logger
from pathlib import Path
from typing import Any

import botocore.exceptions
import requests
from urllib3.exceptions import ProtocolError

from lib.amazon import get_ssm_param
from lib.installation_context import InstallationContext
from lib.library_build_config import LibraryBuildConfig
from lib.library_platform import LibraryPlatform

# Constants
_TIMEOUT = 30
CONANSERVER_URL = "https://conan.compiler-explorer.com"
BUILD_TIMEOUT = 600

CONANINFOHASH_RE = re.compile(r"^ ID: ([0-9a-f]+)$", re.MULTILINE)


class PostFailure(RuntimeError):
    pass


class FetchFailure(RuntimeError):
    pass


@unique
class BuildStatus(Enum):
    Ok = 0
    Failed = 1
    Skipped = 2
    TimedOut = 3


class BaseLibraryBuilder(ABC):
    """Base class for all library builders with common infrastructure."""

    def __init__(
        self,
        logger: Logger,
        language: str,
        libname: str,
        target_name: str,
        sourcefolder: str,
        install_context: InstallationContext,
        buildconfig: LibraryBuildConfig,
    ):
        self.logger = logger
        self.language = language
        self.libname = libname
        self.target_name = target_name
        self.sourcefolder = sourcefolder
        self.install_context = install_context
        self.buildconfig = buildconfig

        # Common state
        self.forcebuild = False
        self.needs_uploading = 0
        self.conanserverproxy_token = None
        self.current_commit_hash = ""
        self.libid = self.libname  # TODO: CE libid might be different from yaml libname

        # Build parameters
        self.current_buildparameters_obj: dict[str, Any] = defaultdict(lambda: [])
        self.current_buildparameters: list[str] = []

        # Caches
        self._conan_hash_cache: dict[str, str | None] = {}
        self._annotations_cache: dict[str, dict] = {}

        # Thread-local HTTP session for future parallelization
        self._thread_local_data = threading.local()
        self._thread_local_data.session = requests.Session()

    @property
    def http_session(self):
        """Thread-local HTTP session."""
        return self._thread_local_data.session

    @abstractmethod
    def completeBuildConfig(self):
        """Complete build configuration - must be implemented by subclasses."""
        pass

    @abstractmethod
    def makebuild(self, buildfor):
        """Main build method - must be implemented by subclasses."""
        pass

    @abstractmethod
    def makebuildfor(self, compiler, options, exe, compiler_type, toolchain, *args):
        """Build for specific configuration - must be implemented by subclasses."""
        pass

    @abstractmethod
    def writeconanfile(self, buildfolder):
        """Write conan file - must be implemented by subclasses."""
        pass

    def get_conan_hash(self, buildfolder: str) -> str | None:
        """Get conan hash for a build folder, with caching."""
        if buildfolder in self._conan_hash_cache:
            self.logger.debug(f"Using cached conan hash for {buildfolder}")
            return self._conan_hash_cache[buildfolder]

        if not self.install_context.dry_run:
            self.logger.debug(["conan", "info", "."] + self.current_buildparameters)
            conaninfo = subprocess.check_output(
                ["conan", "info", "-r", "ceserver", "."] + self.current_buildparameters, cwd=buildfolder
            ).decode("utf-8", "ignore")
            self.logger.debug(conaninfo)
            match = CONANINFOHASH_RE.search(conaninfo, re.MULTILINE)
            if match:
                result = match[1]
                self._conan_hash_cache[buildfolder] = result
                return result

        self._conan_hash_cache[buildfolder] = None
        return None

    def conanproxy_login(self):
        """Login to conan proxy server."""
        url = f"{CONANSERVER_URL}/login"

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
            raise RuntimeError(f"Failed to login to conan proxy: {request}")
        response = json.loads(request.content)
        self.conanserverproxy_token = response["token"]

    def resil_post(self, url, json_data, headers=None):
        """Resilient POST request with retries."""
        for _ in range(3):
            try:
                return self.http_session.post(
                    url, data=json_data, headers=headers, timeout=_TIMEOUT, allow_redirects=False
                )
            except (
                requests.exceptions.Timeout,
                requests.exceptions.ConnectionError,
                ProtocolError,
            ) as e:
                self.logger.warning(f"Got {e} when posting to {url}, retrying")
                time.sleep(1)
            except Exception as e:
                self.logger.warning(f"Got {e} when posting to {url}, retrying")
                time.sleep(1)
        raise RuntimeError(f"Failed to post to {url}")

    def resil_get(self, url: str, stream: bool, timeout: int, headers=None) -> requests.Response | None:
        """Resilient GET request with retries."""
        for _ in range(3):
            try:
                return self.http_session.get(
                    url, stream=stream, timeout=timeout, headers=headers, allow_redirects=False
                )
            except (
                requests.exceptions.Timeout,
                requests.exceptions.ConnectionError,
                ProtocolError,
            ) as e:
                self.logger.warning(f"Got {e} for {url}, retrying")
                time.sleep(1)
            except Exception:
                self.logger.warning(f"Got exception for {url}, retrying")
                time.sleep(1)
        return None

    def get_build_annotations(self, buildfolder):
        """Get build annotations from conan server, with caching."""
        if buildfolder in self._annotations_cache:
            self.logger.debug(f"Using cached annotations for {buildfolder}")
            return self._annotations_cache[buildfolder]

        conanhash = self.get_conan_hash(buildfolder)
        if conanhash is None:
            result = defaultdict(lambda: [])
            self._annotations_cache[buildfolder] = result
            return result

        url = f"{CONANSERVER_URL}/annotations/{self.libname}/{self.target_name}/{conanhash}"
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
        """Get the commit hash for this build."""
        if self.current_commit_hash:
            return self.current_commit_hash

        if os.path.exists(f"{self.sourcefolder}/.git"):
            lastcommitinfo = subprocess.check_output(
                ["git", "log", "--format=%H#%s", "-n", "1"], cwd=self.sourcefolder
            ).decode("utf-8", "ignore")
            match = re.match(r"^([0-9a-f]+)#(.*)$", lastcommitinfo, re.MULTILINE)
            if match:
                self.current_commit_hash = match[1]
            else:
                self.current_commit_hash = self.target_name
                return self.current_commit_hash
        else:
            self.current_commit_hash = self.target_name

        return self.current_commit_hash

    def has_failed_before(self):
        """Check if this build configuration has failed before."""
        url = f"{CONANSERVER_URL}/whathasfailedbefore"
        request = self.resil_post(url, json_data=json.dumps(self.current_buildparameters_obj))
        if not request.ok:
            raise PostFailure(f"Post failure for {url}: {request}")
        else:
            response = json.loads(request.content)
            current_commit = self.get_commit_hash()
            if response["commithash"] == current_commit:
                return response["response"]
            else:
                return False

    def is_already_uploaded(self, buildfolder):
        """Check if build is already uploaded to conan server."""
        conanhash = self.get_conan_hash(buildfolder)
        if conanhash is None:
            return False

        url = f"{CONANSERVER_URL}/conanlibrary/{self.libname}/{self.target_name}/{conanhash}"
        with tempfile.TemporaryFile():
            request = self.resil_get(url, stream=True, timeout=_TIMEOUT)
            if not request:
                return False
            return request.ok

    def set_as_uploaded(self, buildfolder):
        """Mark build as uploaded to conan server."""
        conanhash = self.get_conan_hash(buildfolder)
        if conanhash is None:
            raise RuntimeError(f"Error determining conan hash in {buildfolder}")

        self.logger.info(f"commithash: {conanhash}")

        annotations = self.get_build_annotations(buildfolder)
        if "commithash" not in annotations:
            self.upload_builds()
        annotations["commithash"] = self.get_commit_hash()

        # Platform-specific annotations handling would be in subclasses
        self._add_platform_annotations(annotations, buildfolder)

        headers = {"Content-Type": "application/json", "Authorization": "Bearer " + self.conanserverproxy_token}

        url = f"{CONANSERVER_URL}/annotations/{self.libname}/{self.target_name}/{conanhash}"
        request = self.resil_post(url, json_data=json.dumps(annotations), headers=headers)
        if not request.ok:
            raise PostFailure(f"Post failure for {url}: {request}")

    def _add_platform_annotations(self, annotations, buildfolder):
        """Add platform-specific annotations. Override in subclasses if needed."""
        # Not abstract - subclasses can optionally override this
        return

    def upload_builds(self):
        """Upload builds to conan server."""
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

    def save_build_logging(self, builtok, buildfolder, extralogtext):
        """Save build logging to conan server."""
        if builtok == BuildStatus.Failed:
            url = f"{CONANSERVER_URL}/buildfailed"
        elif builtok == BuildStatus.Ok:
            url = f"{CONANSERVER_URL}/buildsuccess"
        elif builtok == BuildStatus.TimedOut:
            url = f"{CONANSERVER_URL}/buildfailed"
        else:
            return

        # Default implementation for gathering log files
        # Subclasses can override to customize which logs to gather
        logging_data = self._gather_build_logs(buildfolder)

        if builtok == BuildStatus.TimedOut:
            logging_data = logging_data + "\n\n" + "BUILD TIMED OUT!!"

        buildparameters_copy = self.current_buildparameters_obj.copy()
        buildparameters_copy["library"] = self.libname
        buildparameters_copy["library_version"] = self.target_name
        buildparameters_copy["logging"] = logging_data + "\n\n" + extralogtext
        buildparameters_copy["commithash"] = self.get_commit_hash()

        headers = {"Content-Type": "application/json", "Authorization": "Bearer " + self.conanserverproxy_token}

        return self.resil_post(url, json_data=json.dumps(buildparameters_copy), headers=headers)

    def _gather_build_logs(self, buildfolder):
        """Gather build log files. Override in subclasses to customize."""
        # Basic implementation - subclasses can override
        return ""

    def executebuildscript(self, buildfolder):
        """Execute build script."""
        scriptfile = os.path.join(buildfolder, self.script_filename)
        args = self._get_script_args(scriptfile)

        self.logger.info(args)
        if self.install_context.dry_run:
            self.logger.info("Would run %s", args)
            return BuildStatus.Ok
        else:
            try:
                subprocess.check_call(args, cwd=buildfolder, timeout=BUILD_TIMEOUT)
                return BuildStatus.Ok
            except subprocess.CalledProcessError:
                return BuildStatus.Failed
            except subprocess.TimeoutExpired:
                self.logger.error("Build timed out")
                return BuildStatus.TimedOut

    def _get_script_args(self, scriptfile):
        """Get script execution arguments. Override in subclasses."""
        return ["bash", scriptfile]

    def executeconanscript(self, buildfolder):
        """Execute conan script."""
        scriptfile = os.path.join(buildfolder, "conanexport.sh")
        if self.install_context.dry_run:
            return BuildStatus.Ok
        else:
            try:
                subprocess.check_call(["bash", scriptfile], cwd=buildfolder)
                return BuildStatus.Ok
            except subprocess.CalledProcessError:
                return BuildStatus.Failed

    def setCurrentConanBuildParameters(
        self, buildos, buildtype, compilerTypeOrGcc, compiler, libcxx, arch, stdver, extraflags
    ):
        """Set current conan build parameters."""
        self.current_buildparameters_obj = defaultdict(lambda: [])
        self.current_buildparameters_obj["os"] = buildos
        self.current_buildparameters_obj["buildtype"] = buildtype
        if compilerTypeOrGcc:
            self.current_buildparameters_obj["compiler"] = compilerTypeOrGcc
        else:
            self.current_buildparameters_obj["compiler"] = "gcc"
        self.current_buildparameters_obj["compiler_version"] = compiler
        if libcxx:
            self.current_buildparameters_obj["libcxx"] = libcxx
        else:
            self.current_buildparameters_obj["libcxx"] = "libstdc++"
        self.current_buildparameters_obj["arch"] = arch
        self.current_buildparameters_obj["stdver"] = stdver
        self.current_buildparameters_obj["flagcollection"] = extraflags

        self.current_buildparameters = []
        for key, value in self.current_buildparameters_obj.items():
            if key == "flagcollection":
                continue
            self.current_buildparameters.append(f"-s {key}={value}")

    def writeconanscript(self, buildfolder):
        """Write conan export script."""
        scriptfile = os.path.join(buildfolder, "conanexport.sh")
        with open(scriptfile, "w", encoding="utf-8") as f:
            f.write("#!/bin/bash\n")
            f.write("set -ex\n")
            f.write(
                " ".join(
                    [
                        "conan",
                        "export-pkg",
                        ".",
                        f"{self.libname}/{self.target_name}@celibs/trunk",
                        "-r",
                        "ceserver",
                        "--force",
                    ]
                    + self.current_buildparameters
                )
            )
            f.write("\n")

    def writebuildscript(
        self,
        buildfolder,
        sourcefolder,
        compiler,
        options,
        exe,
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
        """Write build script. This is a stub - subclasses should override."""
        # Not abstract - subclasses with different signatures can override this
        return

    def makebuildhash(
        self, compiler, options, toolchain, buildos, buildtype, arch, stdver, stdlib, flagscombination, iteration=None
    ) -> str:
        """Make build hash from configuration."""
        # If iteration is provided (from LibraryBuilder), use simple format
        if iteration is not None:
            flagsstr = "|".join(x for x in flagscombination) if flagscombination else ""
            self.logger.info(
                f"Building {self.libname} {self.target_name} for [{compiler},{options},{toolchain},{buildos},{buildtype},{arch},{stdver},{stdlib},{flagsstr}]"
            )
            return compiler + "_" + str(iteration)

        # Otherwise use SHA256 hash (for Rust/Fortran builders)
        flagsstr = "_".join(flagscombination) if flagscombination else ""
        hasher = hashlib.sha256()
        hasher.update(compiler.encode("utf-8", "ignore"))
        hasher.update(options.encode("utf-8", "ignore"))
        hasher.update(toolchain.encode("utf-8", "ignore"))
        hasher.update(buildos.encode("utf-8", "ignore"))
        hasher.update(buildtype.encode("utf-8", "ignore"))
        hasher.update(arch.encode("utf-8", "ignore"))
        hasher.update(stdver.encode("utf-8", "ignore"))
        hasher.update(stdlib.encode("utf-8", "ignore"))
        hasher.update(flagsstr.encode("utf-8", "ignore"))
        return hasher.hexdigest()

    def build_cleanup(self, buildfolder):
        """Clean up build folder after build."""
        if self.install_context.dry_run:
            self.logger.info(f"Would remove directory {buildfolder} but in dry-run mode")
        else:
            shutil.rmtree(buildfolder, ignore_errors=True)
            self.logger.info(f"Removing {buildfolder}")


class CompilerBasedLibraryBuilder(BaseLibraryBuilder):
    """Base class for compiler-based library builders (C++, Fortran)."""

    def __init__(
        self,
        logger,
        language,
        libname,
        target_name,
        sourcefolder,
        install_context,
        buildconfig,
        popular_compilers_only,
        platform,
    ):
        super().__init__(logger, language, libname, target_name, sourcefolder, install_context, buildconfig)
        self.platform = platform
        self.check_compiler_popularity = popular_compilers_only

        # These will be set by subclasses
        self.compilerprops = {}
        self.libraryprops = {}

        # Script filename depends on platform
        self.script_filename = "cebuild.sh"
        if self.platform == LibraryPlatform.Windows:
            self.script_filename = "cebuild.ps1"

    def getToolchainPathFromOptions(self, options):
        """Get toolchain path from compiler options."""
        match = re.search(r"--gcc-toolchain=(\S*)", options)
        if match:
            return match[1]
        else:
            # Fallback for --gxx-name option (used by some compilers)
            match = re.search(r"--gxx-name=(\S*)", options)
            if match:
                toolchainpath = Path(match[1]).parent / ".."
                return str(toolchainpath.resolve())
        return ""

    def getSysrootPathFromOptions(self, options):
        """Get sysroot path from compiler options."""
        match = re.search(r"--sysroot=(\S*)", options)
        if match:
            return match[1]
        return ""

    def getStdVerFromOptions(self, options):
        """Get C++ standard version from compiler options."""
        match = re.search(r"(?:--std|-std)=(\S*)", options)
        if match:
            return match[1]
        return ""

    def getStdLibFromOptions(self, options):
        """Get stdlib from compiler options."""
        match = re.search(r"-stdlib=(\S*)", options)
        if match:
            return match[1]
        return ""

    def getTargetFromOptions(self, options):
        """Get target from compiler options."""
        match = re.search(r"(?:--target|-target)=(\S*)", options)
        if match:
            return match[1]
        return ""

    def get_compiler_type(self, compiler):
        """Get compiler type from compiler properties."""
        compilerType = ""
        if "compilerType" in self.compilerprops[compiler]:
            compilerType = self.compilerprops[compiler]["compilerType"]
        else:
            raise RuntimeError(f"Something is wrong with {compiler}")

        if self.compilerprops[compiler]["compilerType"] == "clang-intel":
            compilerType = "clang"
        return compilerType

    def does_compiler_support(self, exe, compilerType, arch, options, ldPath):
        """Check if compiler supports the given architecture."""
        if arch == "x86":
            return self.does_compiler_support_x86(exe, compilerType, options, ldPath)
        elif arch == "x86_64":
            return self.does_compiler_support_amd64(exe, compilerType, options, ldPath)
        else:
            return True

    @abstractmethod
    def does_compiler_support_x86(self, exe, compilerType, options, ldPath):
        """Check if compiler supports x86 - must be implemented by subclasses."""
        pass

    @abstractmethod
    def does_compiler_support_amd64(self, exe, compilerType, options, ldPath):
        """Check if compiler supports amd64 - must be implemented by subclasses."""
        pass
