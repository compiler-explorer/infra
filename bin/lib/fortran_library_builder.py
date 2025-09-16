from __future__ import annotations

import contextlib
import glob
import itertools
import os
import re
import shutil
import subprocess
from collections import defaultdict
from collections.abc import Generator
from pathlib import Path
from typing import Any, TextIO

from lib.amazon_properties import get_properties_compilers_and_libraries
from lib.base_library_builder import (
    BuildStatus,
    CompilerBasedLibraryBuilder,
)
from lib.library_build_config import LibraryBuildConfig
from lib.library_platform import LibraryPlatform
from lib.staging import StagingDir

_TIMEOUT = 600

build_supported_os = ["Linux"]
build_supported_buildtype = ["Debug"]
build_supported_arch = ["x86_64"]
build_supported_stdver = [""]
build_supported_stdlib = [""]
build_supported_flags = [""]
build_supported_flagscollection = [[""]]

disable_clang_libcpp = [""]

_propsandlibs: dict[str, Any] = defaultdict(lambda: [])
_supports_x86: dict[str, Any] = defaultdict(lambda: [])

GITCOMMITHASH_RE = re.compile(r"^(\w*)\s.*")
CONANINFOHASH_RE = re.compile(r"\s+ID:\s(\w*)")


def _quote(string: str) -> str:
    return f'"{string}"'


BUILD_TIMEOUT = 600  # Keep for Fortran-specific timeout if needed


@contextlib.contextmanager
def open_script(script: Path) -> Generator[TextIO, None, None]:
    with script.open("w", encoding="utf-8") as f:
        yield f
    script.chmod(0o755)


class FortranLibraryBuilder(CompilerBasedLibraryBuilder):
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
    ):
        super().__init__(
            logger,
            language,
            libname,
            target_name,
            sourcefolder,
            install_context,
            buildconfig,
            popular_compilers_only,
            LibraryPlatform.Linux,
        )

        if self.language in _propsandlibs:
            [self.compilerprops, self.libraryprops] = _propsandlibs[self.language]
        else:
            [self.compilerprops, self.libraryprops] = get_properties_compilers_and_libraries(
                self.language, self.logger, LibraryPlatform.Linux, True
            )
            _propsandlibs[self.language] = [self.compilerprops, self.libraryprops]

        self.completeBuildConfig()

    def does_compiler_support_amd64(self, exe, compilerType, options, ldPath):
        """Fortran compilers generally support amd64."""
        return True

    def does_compiler_support(self, exe, compilerType, arch, options, ldPath):
        fixedTarget = self.getTargetFromOptions(options)
        if fixedTarget:
            return fixedTarget == arch

        fullenv = os.environ
        fullenv["LD_LIBRARY_PATH"] = ldPath

        if not compilerType:
            try:
                output = subprocess.check_output([exe, "--target-help"], env=fullenv).decode("utf-8", "ignore")
            except subprocess.CalledProcessError as e:
                output = e.output.decode("utf-8", "ignore")
        else:
            output = ""

        if arch in output:
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

    def getToolchainPathFromOptions(self, options):
        match = re.search(r"--gcc-toolchain=(\S*)", options)
        if match:
            return match[1]
        else:
            match = re.search(r"--gxx-name=(\S*)", options)
            if match:
                return os.path.realpath(os.path.join(os.path.dirname(match[1]), ".."))
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
        # Align with base class pattern while supporting Fortran compilers
        match = re.search(r"(?:--target|-target)[=\s](\S*)", options)
        if match:
            return match[1]
        return False

    def get_compiler_type(self, compiler):
        compilerType = ""
        if "compilerType" in self.compilerprops[compiler]:
            compilerType = self.compilerprops[compiler]["compilerType"]
        else:
            raise RuntimeError(f"Something is wrong with {compiler}")

        if self.compilerprops[compiler]["compilerType"] == "clang-intel":
            # hack for icpx so we don't get duplicate builds
            # Note: Fortran specifically needs this mapping to gcc
            compilerType = "gcc"

        return compilerType

    def _gather_build_logs(self, buildfolder):
        """Gather Fortran-specific build logs including FPM logs."""
        logging_data = ""
        # Get standard build logs
        if hasattr(super(), "_gather_build_logs"):
            logging_data = super()._gather_build_logs(buildfolder)

        # Add FPM-specific logs
        fpm_logs = glob.glob(os.path.join(buildfolder, "cefpm*.txt"))
        for logfile in fpm_logs:
            with open(logfile, encoding="utf-8") as f:
                logging_data += f"\n\n=== FPM Log: {os.path.basename(logfile)} ===\n"
                logging_data += f.read()

        return logging_data

    def writebuildscript(
        self,
        buildfolder,
        compiler,
        compileroptions,
        compilerexe,
        compilerType,
        toolchain,
        buildos,
        buildtype,
        arch,
        stdver,
        flagscombination,
        ldPath,
    ):
        with open_script(Path(buildfolder) / "cebuild.sh") as f:
            f.write("#!/bin/sh\n\n")

            if compilerexe.endswith("gfortran"):
                compilerexecc = compilerexe[:-7] + "cc"
                compilerexecxx = compilerexe[:-7] + "++"

                f.write(f"export CC={compilerexecc}\n")
                f.write(f"export CXX={compilerexecxx}\n")
            elif (compilerexe.endswith("ifort") or compilerexe.endswith("ifx")) and toolchain:
                compilerexecc = toolchain + "/bin/gcc"
                compilerexecxx = toolchain + "/bin/g++"

                f.write(f"export CC={compilerexecc}\n")
                f.write(f"export CXX={compilerexecxx}\n")

            libparampaths = ["./lib"]

            if os.path.exists(f"{toolchain}/lib64"):
                libparampaths.append(f"{toolchain}/lib64")
                libparampaths.append(f"{toolchain}/lib")
            else:
                libparampaths.append(f"{toolchain}/lib")

            rpathflags = ""
            ldflags = ""
            for path in libparampaths:
                rpathflags += f"-Wl,-rpath={path} "

            for path in libparampaths:
                ldflags += f"-L{path} "

            ldlibpathsstr = ldPath.replace("${exePath}", os.path.dirname(compilerexe)).replace("|", ":")

            libcxx = "std"

            f.write(f'export LD_LIBRARY_PATH="{ldlibpathsstr}"\n')
            f.write(f'export LDFLAGS="{ldflags} {rpathflags}"\n')
            f.write('export NUMCPUS="$(nproc)"\n')

            extraflags = " ".join(x for x in flagscombination)

            compilerTypeOrGcc = compilerType or "fortran"

            fortran_flags = f"{compileroptions} {rpathflags} {extraflags}"

            if self.buildconfig.build_type == "fpm":
                for line in self.buildconfig.prebuild_script:
                    f.write(f"{line}\n")

                f.write(f'export FPM_FC="{compilerexe}"\n')
                f.write(f'export FPM_FFLAGS="{fortran_flags}"\n')
                f.write(f'export FPM_LDFLAGS="{ldflags} {rpathflags}"\n')

                f.write("/opt/compiler-explorer/fpm-0.9.0/fpm build --verbose > cefpmbuildlog.txt 2>&1\n")

            for line in self.buildconfig.postbuild_script:
                f.write(f"{line}\n")

        self.setCurrentConanBuildParameters(
            buildos, buildtype, compilerTypeOrGcc, compiler, libcxx, arch, stdver, extraflags
        )

    def write_conan_file_to(self, f: TextIO) -> None:
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

        for copy_line in self.buildconfig.copy_files:
            f.write(f"        {copy_line}\n")

        f.write('        self.copy("build/*/*.mod", dst="mod", keep_path=False)\n')
        f.write('        self.copy("build/*/*.smod", dst="mod", keep_path=False)\n')
        f.write('        self.copy("build/*/*.a", dst="lib", keep_path=False)\n')

    def writeconanfile(self, buildfolder):
        with (Path(buildfolder) / "conanfile.py").open(mode="w", encoding="utf-8") as f:
            self.write_conan_file_to(f)

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
    ):
        combined_hash = self.makebuildhash(
            compiler, options, toolchain, buildos, buildtype, arch, stdver, stdlib, flagscombination
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
            compiler,
            options,
            exe,
            compiler_type,
            toolchain,
            buildos,
            buildtype,
            arch,
            stdver,
            flagscombination,
            ld_path,
        )

        self.writeconanfile(build_folder)
        extralogtext = ""

        if not self.forcebuild and self.has_failed_before({}):
            self.logger.info("Build has failed before, not re-attempting")
            return BuildStatus.Skipped

        if self.is_already_uploaded(build_folder):
            self.logger.info("Build already uploaded")
            if not self.forcebuild:
                return BuildStatus.Skipped

        if requires_tree_copy:
            shutil.copytree(self.sourcefolder, build_folder, dirs_exist_ok=True)

        if not self.install_context.dry_run and not self.conanserverproxy_token:
            self.conanproxy_login()

        build_status = self.executebuildscript(build_folder)
        if build_status == BuildStatus.Ok:
            self.writeconanscript(build_folder)
            if not self.install_context.dry_run:
                build_status = self.executeconanscript(build_folder)
                if build_status == BuildStatus.Ok:
                    self.needs_uploading += 1
                    self.set_as_uploaded(build_folder, {})

        if not self.install_context.dry_run:
            self.save_build_logging(build_status, build_folder, extralogtext)

        if build_status == BuildStatus.Ok:
            if self.buildconfig.build_type == "fpm":
                self.build_cleanup(build_folder)

        return build_status

    def makebuild(self, buildfor):
        builds_failed = 0
        builds_succeeded = 0
        builds_skipped = 0
        checkcompiler = ""

        if buildfor:
            self.forcebuild = True

        if self.buildconfig.lib_type == "cshared":
            checkcompiler = self.buildconfig.use_compiler
            if checkcompiler not in self.compilerprops:
                self.logger.error(
                    f"Unknown compiler {checkcompiler} to build cshared lib {self.buildconfig.sharedliblink}"
                )
        elif buildfor == "nonx86":
            self.forcebuild = True
            checkcompiler = ""
        elif buildfor == "allclang" or buildfor == "allicc" or buildfor == "allgcc" or buildfor == "forceall":
            self.forcebuild = True
            checkcompiler = ""
        elif buildfor:
            checkcompiler = buildfor
            if checkcompiler not in self.compilerprops:
                self.logger.error(f"Unknown compiler {checkcompiler}")

        for compiler in self.compilerprops:
            if not self.should_build_with_compiler(compiler, checkcompiler, buildfor):
                self.logger.debug(f"Skipping {compiler}")
                continue

            compilerType = self.get_compiler_type(compiler)

            exe = self.compilerprops[compiler]["exe"]

            options = self.compilerprops[compiler]["options"]

            toolchain = self.getToolchainPathFromOptions(options)
            fixedStdver = self.getStdVerFromOptions(options)
            fixedStdlib = self.getStdLibFromOptions(options)

            if not toolchain:
                toolchain = os.path.realpath(os.path.join(os.path.dirname(exe), ".."))

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

            if not self.does_compiler_support_x86(
                exe, compilerType, self.compilerprops[compiler]["options"], self.compilerprops[compiler]["ldPath"]
            ):
                archs = [""]

            if buildfor == "nonx86" and archs[0]:
                continue

            stdvers = build_supported_stdver
            if fixedStdver:
                stdvers = [fixedStdver]

            for args in itertools.product(
                build_supported_os, build_supported_buildtype, archs, stdvers, stdlibs, build_supported_flagscollection
            ):
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
                    )
                    if buildstatus == BuildStatus.Ok:
                        builds_succeeded = builds_succeeded + 1
                    elif buildstatus == BuildStatus.Skipped:
                        builds_skipped = builds_skipped + 1
                    else:
                        builds_failed = builds_failed + 1

            if builds_succeeded > 0:
                self.upload_builds()

        return [builds_succeeded, builds_skipped, builds_failed]
