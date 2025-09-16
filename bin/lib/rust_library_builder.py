from __future__ import annotations

import contextlib
import glob
import itertools
import json
import os
import re
import shutil
import subprocess
from collections import defaultdict
from collections.abc import Generator
from pathlib import Path
from typing import Any, TextIO

from lib.amazon_properties import get_properties_compilers_and_libraries
from lib.base_library_builder import CONANSERVER_URL, BaseLibraryBuilder, BuildStatus, PostFailure
from lib.installation_context import InstallationContext
from lib.library_build_config import LibraryBuildConfig
from lib.library_platform import LibraryPlatform
from lib.rust_crates import RustCrate, get_builder_user_agent_id
from lib.staging import StagingDir

_TIMEOUT = 600
skip_compilers = ["nightly", "beta", "gccrs-snapshot", "mrustc-master", "rustccggcc-master"]

build_supported_os = ["Linux"]
build_supported_buildtype = ["Debug"]
build_supported_arch = ["x86_64"]
build_supported_stdver = [""]
build_supported_stdlib = [""]
build_supported_flags = [""]
build_supported_flagscollection = [[""]]

_propsandlibs: dict[str, Any] = defaultdict(lambda: [])

GITCOMMITHASH_RE = re.compile(r"^(\w*)\s.*")
CONANINFOHASH_RE = re.compile(r"\s+ID:\s(\w*)")


BUILD_TIMEOUT = 600  # Keep for Rust-specific timeout if needed


@contextlib.contextmanager
def open_script(script: Path) -> Generator[TextIO, None, None]:
    with script.open("w", encoding="utf-8") as f:
        yield f
    script.chmod(0o755)


class RustLibraryBuilder(BaseLibraryBuilder):
    def __init__(
        self,
        logger,
        language: str,
        libname: str,
        target_name: str,
        install_context: InstallationContext,
        buildconfig: LibraryBuildConfig,
    ):
        # Rust doesn't have sourcefolder in signature
        super().__init__(logger, language, libname, target_name, "", install_context, buildconfig)

        if self.language in _propsandlibs:
            [self.compilerprops, self.libraryprops] = _propsandlibs[self.language]
        else:
            [self.compilerprops, self.libraryprops] = get_properties_compilers_and_libraries(
                self.language, self.logger, LibraryPlatform.Linux, True
            )
            _propsandlibs[self.language] = [self.compilerprops, self.libraryprops]

        self.cached_source_folders: list[str] = []

        self.completeBuildConfig()

    @property
    def script_filename(self):
        return "cebuild.sh"

    def completeBuildConfig(self):
        if "description" in self.libraryprops[self.libid]:
            self.buildconfig.description = self.libraryprops[self.libid]["description"]
        if "name" in self.libraryprops[self.libid]:
            self.buildconfig.description = self.libraryprops[self.libid]["name"]
        if "url" in self.libraryprops[self.libid]:
            self.buildconfig.url = self.libraryprops[self.libid]["url"]

    def writebuildscript(
        self,
        buildfolder,
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
        build_method,
        logfolder,
    ):
        rustbinpath = os.path.dirname(compilerexe)
        rustpath = os.path.dirname(rustbinpath)
        extraflags = ""
        libcxx = ""

        with open_script(Path(sourcefolder) / "build.sh") as f:
            f.write("#!/bin/sh\n\n")

            f.write(f"export RUSTPATH={rustpath}\n")
            f.write(f"export CARGO={rustbinpath}/cargo\n")

            linkerpath = os.path.join(build_method["linker"], "bin")
            methodflags = build_method["build_method"]

            f.write(f"export PATH={rustbinpath}:{linkerpath}\n")
            f.write(f'export RUSTFLAGS="-C linker={linkerpath}/gcc"\n')

            for line in self.buildconfig.prebuild_script:
                f.write(f"{line}\n")

            if self.buildconfig.build_type == "cargo":
                cargoline = f"$CARGO build {methodflags} --target-dir {buildfolder} > {logfolder}/buildlog.txt 2>&1\n"
                f.write(cargoline)
            else:
                raise RuntimeError(f"Unknown build_type {self.buildconfig.build_type}")

        self.setCurrentConanBuildParameters(
            buildos, buildtype, compilerType, compiler, libcxx, arch, stdver, extraflags
        )

    def setCurrentConanBuildParameters(
        self, buildos, buildtype, compilerTypeOrGcc, compiler, libcxx, arch, stdver, extraflags
    ):
        """Set current conan build parameters for Rust builds."""
        self.current_buildparameters_obj = {}
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
            f"arch={arch}",
            "-s",
            f"stdver={stdver}",
            "-s",
            f"flagcollection={extraflags}",
        ]
        if libcxx:
            self.current_buildparameters.extend(["-s", f"compiler.libcxx={libcxx}"])

    def writeconanscript(self, buildfolder):
        """Write conan export script for Rust packages."""
        conanparamsstr = " ".join(self.current_buildparameters)
        scriptfile = Path(buildfolder) / "conanexport.sh"
        with scriptfile.open("w", encoding="utf-8") as f:
            f.write("#!/bin/sh\n\n")
            f.write(f"conan export-pkg . {self.libname}/{self.target_name} -f {conanparamsstr}\n")
        scriptfile.chmod(0o755)

    def writeconanfile(self, buildfolder):
        underscoredlibname = self.libname.replace("-", "_")
        with (Path(buildfolder) / "conanfile.py").open(mode="w", encoding="utf-8") as f:
            f.write("from conans import ConanFile, tools\n")
            f.write(f"class {underscoredlibname}Conan(ConanFile):\n")
            f.write(f'    name = "{self.libname}"\n')
            f.write(f'    version = "{self.target_name}"\n')
            f.write('    settings = "os", "compiler", "build_type", "arch", "stdver", "flagcollection"\n')
            f.write(f'    description = "{self.buildconfig.description}"\n')
            f.write(f'    url = "{self.buildconfig.url}"\n')
            f.write('    license = "None"\n')
            f.write('    author = "None"\n')
            f.write("    topics = None\n")
            f.write("    def package(self):\n")
            f.write(f'        self.copy("build/*.*", dst="{self.libname}", keep_path=True)\n')

    def countValidLibraryBinaries(self, buildfolder, arch, stdlib):
        filesfound = 1

        return filesfound

    def executeconanscript(self, buildfolder, arch, stdlib):
        filesfound = self.countValidLibraryBinaries(buildfolder, arch, stdlib)
        if filesfound != 0:
            if subprocess.call(["./conanexport.sh"], cwd=buildfolder) == 0:
                self.logger.info("Export succesful")
                return BuildStatus.Ok
            else:
                return BuildStatus.Failed
        else:
            self.logger.info("No binaries found to export")
            return BuildStatus.Failed

    def executebuildscript(self, buildfolder):
        try:
            if subprocess.call(["./build.sh"], cwd=buildfolder, timeout=BUILD_TIMEOUT) == 0:
                self.logger.info(f"Build succeeded in {buildfolder}")
                return BuildStatus.Ok
            else:
                return BuildStatus.Failed
        except subprocess.TimeoutExpired:
            self.logger.info(f"Build timed out and was killed ({buildfolder})")
            return BuildStatus.TimedOut

    def save_build_logging(self, builtok, logfolder, source_folder, build_method):
        if builtok == BuildStatus.Failed:
            url = f"{CONANSERVER_URL}/buildfailed"
        elif builtok == BuildStatus.Ok:
            url = f"{CONANSERVER_URL}/buildsuccess"
        elif builtok == BuildStatus.TimedOut:
            url = f"{CONANSERVER_URL}/buildfailed"
        else:
            return

        loggingfiles = []
        loggingfiles += glob.glob(logfolder + "/buildlog.txt")

        logging_data = ""
        for logfile in loggingfiles:
            logging_data += Path(logfile).read_text(encoding="utf-8")

        if builtok == BuildStatus.TimedOut:
            logging_data = logging_data + "\n\n" + "BUILD TIMED OUT!!"

        buildparameters_copy = self.current_buildparameters_obj.copy()
        buildparameters_copy["logging"] = logging_data
        buildparameters_copy["commithash"] = self.get_commit_hash()

        if builtok != BuildStatus.Ok:
            buildparameters_copy["flagcollection"] = build_method["build_method"]

        headers = {"Content-Type": "application/json", "Authorization": "Bearer " + self.conanserverproxy_token}

        req_data = json.dumps(buildparameters_copy)
        request = self.resil_post(url, req_data, headers)
        if not request.ok:
            raise PostFailure(f"Post failure for {url}: {request}")

    def get_commit_hash(self) -> str:
        return self.target_name

    def has_failed_before(self, build_method=None):
        """Check if this build configuration has failed before.

        Rust override to handle build_method parameter.
        """
        if build_method:
            # Rust-specific: check with build method
            url = f"{CONANSERVER_URL}/hasfailedbefore"
            data = self.current_buildparameters_obj.copy()
            data["flagcollection"] = build_method["build_method"]
            req_data = json.dumps(data)
            request = self.resil_post(url, req_data)
            if not request.ok:
                raise PostFailure(f"Post failure for {url}: {request}")
            else:
                response = json.loads(request.content)
                return response["response"]
        else:
            # Fall back to base implementation
            return super().has_failed_before()

    def is_already_uploaded(self, buildfolder, source_folder=None):
        """Check if build is already uploaded.

        Rust override that checks annotations for commithash.
        """
        annotations = self.get_build_annotations(buildfolder)
        self.logger.debug("Annotations: " + json.dumps(annotations))

        if "commithash" in annotations:
            commithash = self.get_commit_hash()
            return commithash == annotations["commithash"]
        else:
            return False

    def set_as_uploaded(self, buildfolder, source_folder=None, build_method=None):
        conanhash = self.get_conan_hash(buildfolder)
        if conanhash is None:
            raise RuntimeError(f"Error determining conan hash in {buildfolder}")

        self.logger.info(f"conanhash: {conanhash}")

        annotations = self.get_build_annotations(buildfolder)
        if "commithash" not in annotations:
            self.upload_builds()
        annotations["commithash"] = self.get_commit_hash()

        if build_method:
            for key in build_method:
                annotations[key] = build_method[key]

        self.logger.info(annotations)

        headers = {"Content-Type": "application/json", "Authorization": "Bearer " + self.conanserverproxy_token}
        url = f"{CONANSERVER_URL}/annotations/{self.libname}/{self.target_name}/{conanhash}"

        request = self.resil_post(url, json.dumps(annotations), headers)
        if not request.ok:
            raise RuntimeError(f"Post failure for {url}: {request}")

    def clone_branch(self, dest, staging: StagingDir):
        subprocess.check_call(
            ["git", "clone", "-q", f"{self.buildconfig.domainurl}/{self.buildconfig.repo}.git", dest],
            cwd=staging.path,
        )
        subprocess.check_call(["git", "-C", dest, "checkout", "-q", self.target_name], cwd=staging.path)

    def download_library(self, build_folder, source_folder, staging: StagingDir):
        if not os.path.exists(os.path.join(source_folder, "Cargo.toml")):
            self.logger.info(f"Downloading sources for {self.libname}/{self.target_name}")

            if self.buildconfig.repo:
                self.clone_branch(source_folder, staging)
            else:
                crate = RustCrate(self.libname, self.target_name, get_builder_user_agent_id())
                url = crate.GetDownloadUrl()
                tar_cmd = ["tar", "zxf", "-"]
                tar_cmd += ["--strip-components", "1"]
                self.install_context.fetch_url_and_pipe_to(
                    staging, url, command=tar_cmd, subdir=source_folder, agent=get_builder_user_agent_id()
                )

    def get_source_folder(self, source_staging: StagingDir):
        source_folder = os.path.join(source_staging.path, f"crate_{self.libname}_{self.target_name}")
        if source_folder not in self.cached_source_folders:
            if not os.path.exists(source_folder):
                os.mkdir(source_folder)
            self.cached_source_folders.append(source_folder)
        return source_folder

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
        source_staging,
    ):
        with self.install_context.new_staging_dir() as staging:
            build_method = dict({"build_method": "--all-features", "linker": "/opt/compiler-explorer/gcc-11.1.0"})
            build_status = self.makebuildfor_by_method(
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
                build_method,
                staging,
                source_staging,
            )
            if build_status == BuildStatus.Failed or build_status == BuildStatus.Skipped:
                build_method = dict({"build_method": "", "linker": "/opt/compiler-explorer/gcc-11.1.0"})
                build_status = self.makebuildfor_by_method(
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
                    build_method,
                    staging,
                    source_staging,
                )

        return build_status

    def makebuildfor_by_method(
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
        build_method,
        staging: StagingDir,
        source_staging: StagingDir,
    ):
        combined_hash = self.makebuildhash(
            compiler, options, toolchain, buildos, buildtype, arch, stdver, stdlib, flagscombination
        )

        build_folder = os.path.join(staging.path, combined_hash)
        if os.path.exists(build_folder):
            shutil.rmtree(build_folder, ignore_errors=True)
        os.makedirs(build_folder, exist_ok=True)

        self.logger.debug(f"Buildfolder: {build_folder}")

        real_build_folder = os.path.join(build_folder, "build")
        log_folder = os.path.join(build_folder, "log")
        os.makedirs(log_folder, exist_ok=True)

        source_folder = self.get_source_folder(source_staging)

        self.writeconanfile(build_folder)

        self.writebuildscript(
            real_build_folder,
            source_folder,
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
            build_method,
            log_folder,
        )

        if not self.forcebuild and self.has_failed_before(build_method):
            self.logger.info("Build has failed before, not re-attempting")
            return BuildStatus.Skipped

        if self.is_already_uploaded(build_folder, source_folder):
            self.logger.info("Build already uploaded")
            if not self.forcebuild:
                return BuildStatus.Skipped

        self.download_library(build_folder, source_folder, staging)

        if not self.install_context.dry_run and not self.conanserverproxy_token:
            self.conanproxy_login()

        build_status = self.executebuildscript(source_folder)
        if build_status == BuildStatus.Ok:
            self.writeconanscript(build_folder)
            if not self.install_context.dry_run:
                build_status = self.executeconanscript(build_folder, arch, stdlib)
                if build_status == BuildStatus.Ok:
                    self.needs_uploading += 1
                    self.set_as_uploaded(build_folder, source_folder, build_method)
            else:
                filesfound = self.countValidLibraryBinaries(build_folder, arch, stdlib)
                self.logger.debug(f"Number of valid library binaries {filesfound}")

        if not self.install_context.dry_run:
            self.save_build_logging(build_status, log_folder, source_folder, build_method)

        if build_status == BuildStatus.Ok:
            self.build_cleanup(build_folder)
        elif build_status == BuildStatus.Failed:
            self.logger.info("Build has failed")
        elif build_status == BuildStatus.TimedOut:
            self.logger.info("Build has timed out")

        return build_status

    def cache_cleanup(self):
        if not self.install_context.dry_run:
            for folder in self.cached_source_folders:
                shutil.rmtree(folder, ignore_errors=True)
        else:
            self.logger.info("Would clean crate cache, but in dry-run mode")

    def makebuild(self, buildfor):
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
            if checkcompiler not in self.compilerprops:
                self.logger.error(f"Unknown compiler {checkcompiler}")

        with self.install_context.new_staging_dir() as source_staging:
            for compiler in self.compilerprops:
                if checkcompiler and compiler != checkcompiler:
                    continue

                if compiler in self.buildconfig.skip_compilers:
                    self.logger.debug(f"Skipping {compiler}")
                    continue

                if compiler in skip_compilers:
                    self.logger.debug(f"Skipping {compiler}")
                    continue

                # compiler_semver = version.parse(self.compilerprops[compiler]['semver'])
                # if compiler_semver < min_compiler_version:
                #     self.logger.debug(f'Skipping {compiler} (too old)')
                #     continue

                if "compilerType" in self.compilerprops[compiler]:
                    compilerType = self.compilerprops[compiler]["compilerType"]
                else:
                    raise RuntimeError(f"Something is wrong with {compiler}")

                exe = self.compilerprops[compiler]["exe"]
                options = self.compilerprops[compiler]["options"]
                toolchain = ""

                stdlibs = [""]
                archs = build_supported_arch
                stdvers = build_supported_stdver
                ldPath = ""

                for args in itertools.product(
                    build_supported_os,
                    build_supported_buildtype,
                    archs,
                    stdvers,
                    stdlibs,
                    build_supported_flagscollection,
                ):
                    buildstatus = self.makebuildfor(
                        compiler, options, exe, compilerType, toolchain, *args, ldPath, source_staging
                    )
                    if buildstatus == BuildStatus.Ok:
                        builds_succeeded = builds_succeeded + 1
                    elif buildstatus == BuildStatus.Skipped:
                        builds_skipped = builds_skipped + 1
                    else:
                        builds_failed = builds_failed + 1

                if builds_succeeded > 0:
                    self.upload_builds()

            self.cache_cleanup()

        return [builds_succeeded, builds_skipped, builds_failed]
