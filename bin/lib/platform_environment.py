#!/usr/bin/env python3

import os
from pathlib import Path
from typing import Dict

from lib.compiler_info import CompilerInfo
from lib.library_platform import LibraryPlatform


class PlatformEnvironmentManager:
    """Handles cross-platform environment variable management."""

    def __init__(self, platform: LibraryPlatform):
        self.platform = platform

    def get_library_paths(self, compiler: CompilerInfo, toolchain: str, arch: str) -> list:
        """
        Determine library paths for a compiler based on platform and architecture.
        This logic is extracted from library_builder.py writebuildscript()
        """
        libparampaths = []

        if compiler.is_msvc:
            # MSVC uses libPath from compiler properties
            if compiler.lib_path:
                libparampaths = compiler.lib_path.split(";")
        else:
            # Unix-like systems use toolchain-based paths
            if arch == "" or arch == "x86_64":
                # Native arch for the compiler, so most of the time 64, but not always
                if os.path.exists(f"{toolchain}/lib64"):
                    libparampaths.append(f"{toolchain}/lib64")
                    libparampaths.append(f"{toolchain}/lib")
                else:
                    libparampaths.append(f"{toolchain}/lib")
            elif arch == "x86":
                libparampaths.append(f"{toolchain}/lib")
                if os.path.exists(f"{toolchain}/lib32"):
                    libparampaths.append(f"{toolchain}/lib32")

        return libparampaths

    def get_arch_flags(self, compiler: CompilerInfo, arch: str) -> str:
        """
        Get architecture-specific flags for a compiler.
        This logic is extracted from library_builder.py writebuildscript()
        """
        if arch != "x86":
            return ""

        if compiler.compiler_type == "clang" or compiler.compiler_type == "win32-mingw-clang":
            return "-m32"
        elif (
            compiler.compiler_type == ""
            or compiler.compiler_type == "gcc"
            or compiler.compiler_type == "win32-mingw-gcc"
        ):
            return "-march=i386 -m32"

        return ""

    def get_rpath_flags(self, compiler: CompilerInfo, libparampaths: list) -> str:
        """
        Generate rpath flags for Unix-like systems.
        This logic is extracted from library_builder.py writebuildscript()
        """
        if compiler.compiler_type == "edg" or compiler.is_windows_compiler:
            return ""

        rpathflags = ""
        for path in libparampaths:
            rpathflags += f"-Wl,-rpath={path} "

        return rpathflags.strip()

    def get_ld_flags(self, compiler: CompilerInfo, libparampaths: list) -> str:
        """
        Generate linker flags for Unix-like systems.
        This logic is extracted from library_builder.py writebuildscript()
        """
        if compiler.is_msvc:
            return ""

        ldflags = ""
        for path in libparampaths:
            if path != "":
                ldflags += f"-L{path} "

        return ldflags.strip()

    def setup_compiler_environment(self, compiler: CompilerInfo, toolchain: str = "", arch: str = "") -> Dict[str, str]:
        """Set up environment variables for a compiler in a platform-aware way."""
        env = os.environ.copy()

        # Set basic compiler environment
        env["CC"] = compiler.get_c_compiler()
        env["CXX"] = compiler.executable

        # Determine toolchain if not provided
        if not toolchain:
            toolchain = str(Path(compiler.executable).parent / "..")

        # Get library paths
        libparampaths = self.get_library_paths(compiler, toolchain, arch)

        if self.platform == LibraryPlatform.Windows and compiler.is_msvc:
            # Windows MSVC setup
            if compiler.include_path:
                env["INCLUDE"] = compiler.include_path
            if compiler.lib_path:
                env["LIB"] = compiler.lib_path

            # Add compiler directory to PATH
            compiler_dir = str(Path(compiler.executable).parent)
            self._append_to_path(env, compiler_dir)

            # Add x64 path for DLLs (MSVC specific)
            # Extra path is needed for MSVC, because .dll's are placed in the x64 path
            x64_path = Path(compiler.executable).parent / "../x64"
            if x64_path.exists():
                self._append_to_path(env, str(x64_path.resolve()))

        elif self.platform == LibraryPlatform.Windows and (compiler.is_mingw_gcc or compiler.is_mingw_clang):
            # Windows MinGW setup (MinGW GCC/Clang on Windows)
            compiler_dir = str(Path(compiler.executable).parent)
            self._append_to_path(env, compiler_dir)

            # Set up library paths for MinGW
            if compiler.ld_path:
                # On Windows, use semicolon separator instead of colon
                ld_lib_paths = compiler.ld_path.replace("${exePath}", os.path.dirname(compiler.executable)).replace(
                    "|", ";"
                )
                env["LD_LIBRARY_PATH"] = ld_lib_paths

            # Set up LDFLAGS with library paths (no rpath on Windows)
            ldflags = self.get_ld_flags(compiler, libparampaths)
            if ldflags:
                env["LDFLAGS"] = ldflags

        else:
            # Linux/Unix setup
            compiler_dir = str(Path(compiler.executable).parent)
            self._append_to_path(env, compiler_dir)

            # Set up LD_LIBRARY_PATH
            if compiler.ld_path:
                ld_lib_paths = compiler.ld_path.replace("${exePath}", os.path.dirname(compiler.executable)).replace(
                    "|", ":"
                )
                env["LD_LIBRARY_PATH"] = ld_lib_paths

            # Set up LDFLAGS with library paths and rpath
            ldflags = self.get_ld_flags(compiler, libparampaths)
            rpathflags = self.get_rpath_flags(compiler, libparampaths)
            if ldflags or rpathflags:
                env["LDFLAGS"] = f"{ldflags} {rpathflags}".strip()

        # Set compiler flags if available
        if compiler.options:
            env["CFLAGS"] = compiler.options
            env["CXXFLAGS"] = compiler.options

        return env

    def _append_to_path(self, env: Dict[str, str], path: str) -> None:
        """Append a path to the PATH environment variable in a platform-specific way."""
        separator = ";" if self.platform == LibraryPlatform.Windows else ":"
        if "PATH" in env:
            env["PATH"] = f"{path}{separator}{env['PATH']}"
        else:
            env["PATH"] = path

    def script_env_command(self, var_name: str, var_value: str) -> str:
        """Generate platform-specific environment variable setting command for scripts."""
        if self.platform == LibraryPlatform.Linux:
            return f'export {var_name}="{var_value}"\n'
        elif self.platform == LibraryPlatform.Windows:
            escaped_var_value = var_value.replace('"', '`"')
            return f'$env:{var_name}="{escaped_var_value}"\n'
        else:
            raise ValueError(f"Unsupported platform: {self.platform}")