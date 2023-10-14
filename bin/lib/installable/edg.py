from __future__ import annotations

import logging
import tempfile
from typing import Dict, Any, Callable

import shlex
import subprocess
from lib import amazon
from lib.installable.archives import NonFreeS3TarballInstallable
from lib.installation_context import InstallationContext
from lib.staging import StagingDir
from pathlib import Path

_LOGGER = logging.getLogger(__name__)

_COMMON_EDG_SETUP = """
export CPFE="$EDG_INSTALL_DIR/bin/cpfe"
export ECCP_LIBDIR="$EDG_INSTALL_DIR/lib"
export EDG_MUNCH_PATH="$EDG_INSTALL_DIR/bin/edg_munch"
export EDG_DECODE_PATH="$EDG_INSTALL_DIR/bin/edg_decode"
export EDG_PRELINK_PATH="$EDG_INSTALL_DIR/bin/edg_prelink"
export ECCP="$EDG_INSTALL_DIR/bin/eccp"
export EDG_RUNTIME_LIB="edgrt"
"""


def _shim_gcc_shell(install_dir: Path, gcc: Path, c_includes: str, cpp_includes: str, version: str) -> str:
    return f"""#!/bin/bash
set -euo pipefail

export EDG_INSTALL_DIR="{install_dir}"
export EDG_GCC_INCL_SCRAPE="{cpp_includes}"
export EDG_GCC_CINCL_SCRAPE="{c_includes}"
export EDG_CPFE_DEFAULT_OPTIONS="--gnu {version}"
export EDG_C_TO_OBJ_COMPILER="{gcc}"
# several variables removed

# Set environment variables related to the compiler explorer configuration.
export EDG_BASE="$EDG_INSTALL_DIR/bases/gnu"
{_COMMON_EDG_SETUP}

# Add options for static linking.
export EDG_OBJ_TO_EXEC_DEFAULT_OPTIONS="-static -z muldefs"

# Execute the real eccp driver script.
exec "$EDG_INSTALL_DIR/bin/eccp" $@
"""


def _shim_default_shell(install_dir: Path, gcc: Path, **_kwargs) -> str:
    return f"""#!/bin/bash
#!/bin/bash
set -euo pipefail

export EDG_INSTALL_DIR="{install_dir}"
export EDG_C_TO_OBJ_COMPILER="{gcc}"

# Set environment variables related to the compiler explorer configuration.
export EDG_BASE="$EDG_INSTALL_DIR/bases/default"
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
        self._macro_gen = self.config_get("macro_gen")
        self._macro_dir = self.config_get("macro_output_dir")
        self._scape_cmd = self.config_get("scrape_cmd")
        self._compiler_type = self.config_get("compiler_type")
        self._shim_shell_func = _SHIM_SHELL_FUNCS[self._compiler_type]
        self.install_path = self.config_get("path_name")
        self._setup_check_exe(self.install_path)

    def stage(self, staging: StagingDir) -> None:
        super().stage(staging)
        if len(self.depends) != 1:
            raise RuntimeError("Assumes we have the backend compiler as a dep")
        backend_path = self.install_context.destination / self.depends[0].install_path

        unzip_dir = staging.path
        unzip_dir.mkdir(exist_ok=True, parents=True)

        def _call(checked_command):
            _LOGGER.info("Running %s", shlex.join(checked_command))
            subprocess.check_call(checked_command, cwd=unzip_dir)

        compiler_path = backend_path / "bin" / self._compiler_type

        def _query(lang: str, query_type: str) -> str:
            command_to_run = [
                self._scape_cmd,
                f"--compiler-path={compiler_path}",
                f"--lang={lang}",
                self._compiler_type,
                query_type,
            ]
            _LOGGER.info("Running %s", shlex.join(command_to_run))
            return subprocess.check_output(command_to_run, cwd=unzip_dir).decode("utf-8").strip()

        if self._compiler_type != "default":
            with tempfile.NamedTemporaryFile() as temp_file:
                amazon.s3_client.download_fileobj("compiler-explorer", f"opt-nonfree/{self._scraper}", temp_file)
                temp_file.flush()
                _call(["unzip", temp_file.name])
                cpp_includes = _query("c++", "includes")
                c_includes = _query("c", "includes")
                version = _query("c", "version")

            with tempfile.NamedTemporaryFile() as temp_file:
                amazon.s3_client.download_fileobj("compiler-explorer", f"opt-nonfree/{self._macro_gen}", temp_file)
                temp_file.flush()
                command = ["bash", temp_file.name, f"--{self._compiler_type}", str(compiler_path)]
                _LOGGER.info("Running %s", shlex.join(command))
                subprocess.check_call(command, cwd=staging.path / self.untar_dir / self._macro_dir)
        else:
            cpp_includes = ""
            c_includes = ""
            version = ""

        output_path = staging.path / self.untar_dir / "eccp-scripts"
        output_path.mkdir(exist_ok=True)
        script_path = output_path / f"eccp-{self._compiler_type}"
        with script_path.open("w") as out:
            out.write(
                self._shim_shell_func(
                    install_dir=self.install_context.destination / self.install_path,
                    gcc=compiler_path,
                    c_includes=c_includes,
                    cpp_includes=cpp_includes,
                    version=version,
                )
            )
        script_path.chmod(0o755)

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
            self.install_context.make_subdir(self.install_path)
            self.install_context.move_from_staging(staging, self.untar_dir, self.install_path)

    def __repr__(self) -> str:
        return f"EdgCompilerInstallable({self.name}, {self.install_path})"
