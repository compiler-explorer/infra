from __future__ import annotations

import logging
import shlex
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict

from lib import amazon
from lib.installable.archives import NonFreeS3TarballInstallable
from lib.installation_context import InstallationContext
from lib.staging import StagingDir

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class EdgBackendCompilerScrape:
    c_includes: str
    cpp_includes: str
    version: str


_COMMON_EDG_SETUP = """
export CPFE="$EDG_INSTALL_DIR/bin/cpfe"
export ECCP_LIBDIR="$EDG_INSTALL_DIR/lib"
export EDG_MUNCH_PATH="$EDG_INSTALL_DIR/bin/edg_munch"
export EDG_DECODE_PATH="$EDG_INSTALL_DIR/bin/edg_decode"
export EDG_PRELINK_PATH="$EDG_INSTALL_DIR/bin/edg_prelink"
export ECCP="$EDG_INSTALL_DIR/bin/eccp"
export EDG_RUNTIME_LIB="edgrt"
export EDG_C_TO_OBJ_DEFAULT_OPTIONS="-w"
"""


def _shim_gcc_shell(install_dir: Path, gcc: Path, scrape_info: EdgBackendCompilerScrape) -> str:
    return f"""#!/bin/bash
set -euo pipefail

export EDG_INSTALL_DIR="{install_dir}"
export EDG_GCC_INCL_SCRAPE="{scrape_info.cpp_includes}"
export EDG_GCC_CINCL_SCRAPE="{scrape_info.c_includes}"
export EDG_CPFE_DEFAULT_OPTIONS="--gnu {scrape_info.version}"
export EDG_C_TO_OBJ_COMPILER="{gcc}"

# Set environment variables related to the compiler explorer configuration.
export EDG_BASE="$EDG_INSTALL_DIR/base"
{_COMMON_EDG_SETUP}

# Add options for static linking.
export EDG_OBJ_TO_EXEC_DEFAULT_OPTIONS="-static -z muldefs"

# Execute the real eccp driver script.
exec "$EDG_INSTALL_DIR/bin/eccp" $@
"""


def _shim_default_shell(install_dir: Path, gcc: Path, **_kwargs) -> str:
    return f"""#!/bin/bash
set -euo pipefail

export EDG_INSTALL_DIR="{install_dir}"
export EDG_C_TO_OBJ_COMPILER="{gcc}"

# Set environment variables related to the compiler explorer configuration.
export EDG_BASE="$EDG_INSTALL_DIR/base"
{_COMMON_EDG_SETUP}

# Execute the real eccp driver script.
exec "$EDG_INSTALL_DIR/bin/eccp" $@
"""


_SHIM_SHELL_FUNCS: dict[str, Callable[..., str]] = {
    "default": _shim_default_shell,
    "gcc": _shim_gcc_shell,
}


class EdgCompilerInstallable(NonFreeS3TarballInstallable):
    def __init__(self, install_context: InstallationContext, config: Dict[str, Any]):
        super().__init__(install_context, config)
        self._scraper = self.config_get("scraper")
        self._macro_gen = self.config_get("macro_gen", "")
        self._macro_dir = self.config_get("macro_output_dir", "")
        self._scrape_cmd = self.config_get("scrape_cmd")
        self._compiler_type = self.config_get("compiler_type")
        self.install_path = self.config_get("path_name")

    def _resolve_backend_install_path(self) -> Path:
        if len(self.depends) != 1:
            raise RuntimeError("Assumes we have the backend compiler as a dep")
        return self.install_context.destination / self.depends[0].install_path

    def _resolve_backend_compiler(self) -> Path:
        """The EDG front end generates C files and thus uses a backing C
        compiler complete compilation. Return the path of the backend
        compiler.
        """
        backend_path = self._resolve_backend_install_path()
        if self._compiler_type == "default":
            return backend_path / "bin" / "gcc"
        else:
            return backend_path / "bin" / self._compiler_type

    def _resolve_emulated_c_compiler(self) -> Path:
        """The EDG front end emulates a C and C++ compiler. Return the path of
        the emulated C compiler.
        """
        backend_path = self._resolve_backend_install_path()
        if self._compiler_type == "gcc":
            # For gcc, the emulated C compiler is gcc.
            return backend_path / "bin" / "gcc"
        else:
            # Currently only GCC emulation is supported on Compiler Explorer.
            raise AssertionError(f"Emulation of the {self._compiler_type} C compiler family is not supported")

    def _resolve_emulated_cpp_compiler(self) -> Path:
        """The EDG front end generates C files and thus uses a backing C
        compiler complete compilation. Return the path of the backend
        compiler.
        """
        backend_path = self._resolve_backend_install_path()
        if self._compiler_type == "gcc":
            # For gcc, the emulated C++ compiler is g++.
            return backend_path / "bin" / "g++"
        else:
            # Currently only GCC emulation is supported on Compiler Explorer.
            raise AssertionError(f"Emulation of the {self._compiler_type} C++ compiler family is not supported")

    def _scrape_backend_compiler(self, staging: StagingDir, backend_compiler_path: Path) -> EdgBackendCompilerScrape:
        """The EDG front end when emulating a compiler needs to know that
        compiler's include paths and version. Collect and return the
        aforementioned details if relevant.
        """
        # If the compiler is in default mode the backend compiler isn't scraped.
        if self._compiler_type == "default":
            return EdgBackendCompilerScrape("", "", "")

        scrapper_unzip_dir = staging.path / "backend-scrapping"
        scrapper_unzip_dir.mkdir(exist_ok=True, parents=True)

        def _query(lang: str, query_type: str) -> str:
            """Query the EDG compiler scrape tool for the given language and query type."""
            command_to_run = [
                self._scrape_cmd,
                f"--compiler-path={backend_compiler_path}",
                f"--lang={lang}",
                self._compiler_type,
                query_type,
            ]
            _LOGGER.info("Running %s", shlex.join(command_to_run))
            return subprocess.check_output(command_to_run, cwd=scrapper_unzip_dir).decode("utf-8").strip()

        # Gather the C and C++ include paths as well as the emulated compiler version number.
        with tempfile.NamedTemporaryFile() as temp_file:
            amazon.s3_client.download_fileobj("compiler-explorer", f"opt-nonfree/{self._scraper}", temp_file)
            temp_file.flush()
            command = ["unzip", temp_file.name]
            _LOGGER.info("Running %s", shlex.join(command))
            subprocess.check_call(command, cwd=scrapper_unzip_dir)
            c_includes = _query("c", "includes")
            cpp_includes = _query("c++", "includes")
            version = _query("c", "version")
            return EdgBackendCompilerScrape(c_includes, cpp_includes, version)

    def _write_emulated_predefined_macros(
        self, staging: StagingDir, emulated_c_compiler_path: Path, emulated_cpp_compiler_path: Path
    ) -> None:
        """The EDG front end when emulating a compiler needs to know what
        predefined macros to set. Write the predefined macros file.
        """
        # If the compiler is in default mode the default predefined macros are used.
        assert self._compiler_type != "default"

        # Check some prerequisites before doing further work.
        if len(self._macro_gen) == 0 or len(self._macro_dir) == 0:
            raise RuntimeError("No macro generation script provided for non-default mode EDG compiler")

        # Gather the predefined macros for the emulated compiler.
        with tempfile.NamedTemporaryFile() as temp_file:
            amazon.s3_client.download_fileobj("compiler-explorer", f"opt-nonfree/{self._macro_gen}", temp_file)
            temp_file.flush()
            if self._compiler_type == "gcc":
                command_args = ["--g++", str(emulated_cpp_compiler_path), "--gcc", str(emulated_c_compiler_path)]
            elif self._compiler_type == "clang":
                assert emulated_c_compiler_path == emulated_cpp_compiler_path, (
                    "The emulate clang C and C++ compiler should be the same binary"
                )
                command_args = ["--clang", str(emulated_cpp_compiler_path)]
            else:
                raise AssertionError(f"Cannot generate macros for {self._compiler_type}")

            command = ["bash", temp_file.name, *command_args]
            _LOGGER.info("Running %s", shlex.join(command))
            output_path = staging.path / self.untar_dir / self._macro_dir
            output_path.mkdir(parents=True, exist_ok=True)
            subprocess.check_call(command, cwd=output_path)

    def _write_compiler_shim(
        self, staging: StagingDir, backend_compiler_path: Path, backend_compiler_scrape: EdgBackendCompilerScrape
    ) -> None:
        """The EDG front end is configured via a "shim" script in compiler
        explorer. Generate this shim script with the collected information.
        """
        output_path = staging.path / self.untar_dir / "eccp-scripts"
        output_path.mkdir(parents=True, exist_ok=True)
        script_path = output_path / f"eccp-{self._compiler_type}"
        with script_path.open("w") as out:
            out.write(
                _SHIM_SHELL_FUNCS[self._compiler_type](
                    install_dir=self.install_context.destination / self.install_path,
                    gcc=backend_compiler_path,
                    scrape_info=backend_compiler_scrape,
                )
            )
        script_path.chmod(0o755)

    def stage(self, staging: StagingDir) -> None:
        super().stage(staging)

        if self._compiler_type != "default":
            emulated_c_compiler_path = self._resolve_emulated_c_compiler()
            emulated_cpp_compiler_path = self._resolve_emulated_cpp_compiler()
            self._write_emulated_predefined_macros(staging, emulated_c_compiler_path, emulated_cpp_compiler_path)

        backend_compiler_path = self._resolve_backend_compiler()
        backend_compiler_scrape = self._scrape_backend_compiler(staging, backend_compiler_path)
        self._write_compiler_shim(staging, backend_compiler_path, backend_compiler_scrape)

    def verify(self) -> bool:
        if not super().verify():
            return False
        with self.install_context.new_staging_dir() as staging:
            self.stage(staging)
            return self.install_context.compare_against_staging(staging, self.untar_dir, self.install_path)

    def install(self) -> None:
        super().install()
        with self.install_context.new_staging_dir() as staging:
            self.stage(staging)
            self.install_context.move_from_staging(staging, self.untar_dir, self.install_path)

    def __repr__(self) -> str:
        return f"EdgCompilerInstallable({self.name}, {self.install_path})"
