#!/usr/bin/env python3

from pathlib import Path


class CompilerInfo:
    """Typed wrapper around compiler properties with convenience methods."""

    def __init__(self, compiler_id: str, props: dict):
        self.id = compiler_id
        self._props = props

    @property
    def executable(self) -> str:
        return self._props.get("exe", "")

    @property
    def compiler_type(self) -> str:
        return self._props.get("compilerType", "")

    @property
    def options(self) -> str:
        return self._props.get("options", "")

    @property
    def include_path(self) -> str:
        return self._props.get("includePath", "")

    @property
    def lib_path(self) -> str:
        return self._props.get("libPath", "")

    @property
    def ld_path(self) -> str:
        return self._props.get("ldPath", "")

    @property
    def is_msvc(self) -> bool:
        return self.compiler_type == "win32-vc"

    @property
    def is_mingw_gcc(self) -> bool:
        return self.compiler_type == "win32-mingw-gcc"

    @property
    def is_mingw_clang(self) -> bool:
        return self.compiler_type == "win32-mingw-clang"

    @property
    def is_windows_compiler(self) -> bool:
        return self.is_msvc or self.is_mingw_gcc or self.is_mingw_clang

    @property
    def is_clang(self) -> bool:
        return self.compiler_type == "clang"

    @property
    def is_gcc_like(self) -> bool:
        return self.compiler_type in ["", "gcc"]

    @property
    def exists(self) -> bool:
        """Check if the compiler executable exists on the filesystem."""
        return bool(self.executable and Path(self.executable).exists())

    def get_c_compiler(self) -> str:
        """
        Derive C compiler path from C++ compiler path.
        This logic is extracted from library_builder.py writebuildscript()
        """
        exe = self.executable

        # Special case for EDG compilers
        if self.compiler_type == "edg":
            return exe

        # Windows executable handling
        if exe.endswith(".exe"):
            compilerexecc = exe.replace("++.exe", "")
            if exe.endswith("clang++.exe"):
                compilerexecc = f"{compilerexecc}.exe"
            elif exe.endswith("g++.exe"):
                compilerexecc = f"{compilerexecc}cc.exe"
            elif self.compiler_type == "edg":
                compilerexecc = exe
            else:
                if not compilerexecc.endswith(".exe"):
                    compilerexecc = compilerexecc + ".exe"
            return compilerexecc

        # Linux/Unix executable handling
        else:
            compilerexecc = exe[:-2]  # Remove last 2 chars (++)
            if exe.endswith("clang++"):
                compilerexecc = f"{compilerexecc}"  # clang++ -> clang
            elif exe.endswith("g++"):
                compilerexecc = f"{compilerexecc}cc"  # g++ -> gcc
            elif self.compiler_type == "edg":
                compilerexecc = exe
            return compilerexecc
