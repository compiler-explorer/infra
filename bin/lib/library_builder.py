from __future__ import annotations

import contextlib
import csv
import glob
import itertools
import os
import re
import shutil
import subprocess
import tempfile
from collections import defaultdict
from collections.abc import Generator
from pathlib import Path
from typing import Any, TextIO

from lib.amazon_properties import get_properties_compilers_and_libraries, get_specific_library_version_details
from lib.base_library_builder import (
    BuildStatus,
    CompilerBasedLibraryBuilder,
    FetchFailure,
)
from lib.binary_info import BinaryInfo
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
CONANINFOHASH_RE = re.compile(r"\s+ID:\s(\w*)")


def _quote(string: str) -> str:
    return f'"{string}"'


@contextlib.contextmanager
def open_script(script: Path) -> Generator[TextIO, None, None]:
    with script.open("w", encoding="utf-8") as f:
        yield f
    script.chmod(0o755)


class LibraryBuilder(CompilerBasedLibraryBuilder):
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
        super().__init__(
            logger,
            language,
            libname,
            target_name,
            sourcefolder,
            install_context,
            buildconfig,
            popular_compilers_only,
            platform,
        )

        # C++-specific initialization
        self.current_commit_hash = ""

        self.history = LibraryBuildHistory(self.logger)

        if self.language in _propsandlibs:
            [self.compilerprops, self.libraryprops] = _propsandlibs[self.language]
        else:
            [self.compilerprops, self.libraryprops] = get_properties_compilers_and_libraries(
                self.language, self.logger, self.platform, True
            )
            _propsandlibs[self.language] = [self.compilerprops, self.libraryprops]

        self.completeBuildConfig()

    def _add_platform_annotations(self, annotations, buildfolder):
        """Add C++-specific platform annotations."""
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
            c_flags = f"{compileroptions} {archflag} {extraflags}"
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
                    f"> cecmakelog.txt 2>&1\n"
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
                        f.write(f"cmake --build . {extramakeargs} > cemakelog_.txt 2>&1\n")
                    else:
                        for lognum, target in enumerate(self.buildconfig.make_targets):
                            f.write(
                                f"cmake --build . {extramakeargs} --target={target} > cemakelog_{lognum}.txt 2>&1\n"
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
                    f.write("cmake --install . > ceinstall_0.txt 2>&1\n")
            else:
                if os.path.exists(os.path.join(sourcefolder, "Makefile")):
                    f.write("make clean || /bin/true\n")
                f.write("rm -f *.so*\n")
                f.write("rm -f *.a\n")
                f.write(self.script_env("CXXFLAGS", cxx_flags))
                f.write(self.script_env("CFLAGS", c_flags))
                if self.buildconfig.build_type == "make":
                    configurepath = os.path.join(sourcefolder, "configure")
                    if os.path.exists(configurepath):
                        if self.buildconfig.package_install:
                            f.write(f"./configure {configure_flags} --prefix={installfolder} > ceconfiglog.txt 2>&1\n")
                        else:
                            f.write(f"./configure {configure_flags} > ceconfiglog.txt 2>&1\n")

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
                        f.write(f"{make_utility} {extramakeargs} {target} > cemakelog_{lognum}.txt 2>&1\n")
                else:
                    lognum = 0
                    for lib in itertools.chain(self.buildconfig.staticliblink, self.buildconfig.sharedliblink):
                        f.write(f"{make_utility} {extramakeargs} {lib} > cemakelog_{lognum}.txt 2>&1\n")
                        lognum += 1

                    if not self.buildconfig.package_install:
                        if self.platform == LibraryPlatform.Linux:
                            if len(self.buildconfig.staticliblink) != 0:
                                f.write("libsfound=$(find . -iname 'lib*.a')\n")
                            elif len(self.buildconfig.sharedliblink) != 0:
                                f.write("libsfound=$(find . -iname 'lib*.so*')\n")

                            f.write('if [ "$libsfound" = "" ]; then\n')
                            f.write(f"  {make_utility} {extramakeargs} all > cemakelog_{lognum}.txt 2>&1\n")
                            f.write("fi\n")
                        elif self.platform == LibraryPlatform.Windows:
                            f.write("$libs = Get-Childitem -Path ./**.lib -Recurse -ErrorAction SilentlyContinue\n")
                            f.write("if ($libs.count -eq 0) {\n")
                            f.write(f"  {make_utility} {extramakeargs} all > cemakelog_{lognum}.txt 2>&1\n")
                            f.write("}\n")

                if self.buildconfig.package_install:
                    f.write(f"{make_utility} install > ceinstall_0.txt 2>&1\n")

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
        headerfiles += glob.glob(str(buildfolder / "*.h"), recursive=True)
        headerfiles += glob.glob(str(buildfolder / "*.hpp"), recursive=True)
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

        if self.check_compiler_popularity:
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

            if builds_succeeded > 0:
                self.upload_builds()

        return [builds_succeeded, builds_skipped, builds_failed]
