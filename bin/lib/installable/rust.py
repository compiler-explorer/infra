from __future__ import annotations

import functools
import os
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any

from lib.amazon import list_s3_artifacts
from lib.installable.installable import Installable
from lib.installation_context import InstallationContext
from lib.staging import StagingDir

import logging

_LOGGER = logging.getLogger(__name__)


@functools.lru_cache(maxsize=512)
def s3_available_rust_artifacts(prefix):
    dist_prefix = "dist/"
    return [
        compiler[len(dist_prefix) :]
        for compiler in list_s3_artifacts("static-rust-lang-org", dist_prefix + prefix)
        if compiler.endswith(".tar.gz")
    ]


class RustInstallable(Installable):
    def __init__(self, install_context: InstallationContext, config: Dict[str, Any]):
        super().__init__(install_context, config)
        self.install_path = self.config_get("dir")
        self._setup_check_exe(self.install_path)
        self.base_package = self.config_get("base_package")
        self.nightly_install_days = self.config_get("nightly_install_days", 0)
        self.patchelf = self.config_get("patchelf")
        self.depends_by_name.append(self.patchelf)

    @property
    def nightly_like(self) -> bool:
        return self.nightly_install_days > 0

    def do_rust_install(self, staging: StagingDir, component: str, install_to: Path) -> None:
        url = f"https://static.rust-lang.org/dist/{component}.tar.gz"
        untar_to = staging.path / "__temp_install__"
        self.install_context.fetch_url_and_pipe_to(staging, url, ["tar", "zxf", "-", "--strip-components=1"], untar_to)
        self.install_context.stage_command(
            staging, ["./install.sh", f"--prefix={install_to}", "--verbose", "--without=rust-docs"], cwd=untar_to
        )
        self.install_context.remove_dir(untar_to)

    def set_rpath(self, elf_file: Path, rpath: str) -> None:
        patchelf = (
            self.install_context.destination / self.find_dependee(self.patchelf).install_path / "bin" / "patchelf"
        )
        _LOGGER.info("Setting rpath of %s to %s", elf_file, rpath)
        subprocess.check_call([patchelf, "--set-rpath", rpath, elf_file])

    def stage(self, staging: StagingDir) -> None:
        arch_std_prefix = f"rust-std-{self.target_name}-"
        suffix = ".tar.gz"
        architectures = [
            artifact[len(arch_std_prefix) : -len(suffix)] for artifact in s3_available_rust_artifacts(arch_std_prefix)
        ]
        self._logger.info("Installing for these architectures: %s", ", ".join(architectures or ["none"]))
        base_path = staging.path / f"rust-{self.target_name}"
        self.do_rust_install(staging, self.base_package, base_path)
        for architecture in architectures:
            self.do_rust_install(staging, f"rust-std-{self.target_name}-{architecture}", base_path)
        for binary in (b for b in (base_path / "bin").glob("*") if self.install_context.is_elf(b)):
            self.set_rpath(binary, "$ORIGIN/../lib")
        for shared_object in (base_path / "lib").glob("*.so"):
            self.set_rpath(shared_object, "$ORIGIN")
        self.install_context.remove_dir(base_path / "share")

    def should_install(self) -> bool:
        if self.nightly_install_days > 0:
            dest_dir = self.install_context.destination / self.install_path
            if os.path.exists(dest_dir):
                dtime = datetime.fromtimestamp(dest_dir.stat().st_mtime)
                # The fudge factor of 30m is to sort of account for the installation time. Else
                # we start up the same time the next day and we get a 23hr58 minute old build and we
                # don't reinstall.
                age = datetime.now() - dtime + timedelta(minutes=30)
                self._logger.info("Nightly build %s is %s old", dest_dir, age)
                if age.days > self.nightly_install_days:
                    return True
        return super().should_install()

    def verify(self) -> bool:
        if not super().verify():
            return False
        with self.install_context.new_staging_dir() as staging:
            self.stage(staging)
            return self.install_context.compare_against_staging(staging, self.install_path)

    def install(self) -> None:
        super().install()
        with self.install_context.new_staging_dir() as staging:
            self.stage(staging)
            self.install_context.move_from_staging(staging, self.install_path)

    def __repr__(self) -> str:
        return f"RustInstallable({self.name}, {self.install_path})"


class CratesIOInstallable(Installable):
    def is_installed(self) -> bool:
        return True
