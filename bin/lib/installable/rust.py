from __future__ import annotations

import functools
import logging
import os
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from lib.amazon import list_s3_artifacts
from lib.installable.installable import Installable
from lib.installation_context import InstallationContext
from lib.staging import StagingDir

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
    def __init__(self, install_context: InstallationContext, config: dict[str, Any]):
        super().__init__(install_context, config)
        self.install_path = self.config_get("dir")
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
            staging, ["./install.sh", f"--prefix={install_to}", "--verbose"], cwd=untar_to
        )
        self.install_context.remove_dir(untar_to)

    def maybe_set_rpath(self, maybe_elf_file: Path, rpath: str) -> None:
        if not self.install_context.is_elf(maybe_elf_file):
            _LOGGER.info("Skipping rpath set of %s as it's not an ELF file", maybe_elf_file)
            return
        patchelf = (
            self.install_context.destination / self.find_dependee(self.patchelf).install_path / "bin" / "patchelf"
        )
        _LOGGER.info("Setting rpath of %s to %s", maybe_elf_file, rpath)
        subprocess.check_call([patchelf, "--set-rpath", rpath, maybe_elf_file])

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
        for binary in (base_path / "bin").glob("*"):
            self.maybe_set_rpath(binary, "$ORIGIN/../lib")
        for shared_object in (base_path / "lib").glob("*.so"):
            self.maybe_set_rpath(shared_object, "$ORIGIN")
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
            self.install_context.move_from_staging(staging, self.name, self.install_path)

    def __repr__(self) -> str:
        return f"RustInstallable({self.name}, {self.install_path})"


class CratesIOInstallable(Installable):
    def is_installed(self) -> bool:
        return True

    @property
    def is_squashable(self) -> bool:
        return False
