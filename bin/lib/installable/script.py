from __future__ import annotations

import shutil
from pathlib import Path
from typing import Dict, Any

from lib.installable.installable import Installable
from lib.installation_context import InstallationContext
from lib.staging import StagingDir


class ScriptInstallable(Installable):
    def __init__(self, install_context: InstallationContext, config: Dict[str, Any]):
        super().__init__(install_context, config)
        self.install_path = self.config_get("dir")
        self.install_path_symlink = self.config_get("symlink", False)
        self.fetch = self.config_get("fetch")
        self.script = self.config_get("script")
        self.strip = self.config_get("strip", False)
        self._setup_check_exe(self.install_path)
        if self.install_path_symlink:
            self._setup_check_link(self.install_path, self.install_path_symlink)

    def stage(self, staging: StagingDir) -> None:
        for url in self.fetch:
            url, filename = url.split(" ")
            staging_path_filename = staging.path / filename
            if url[:1] == "/":
                shutil.copyfile(url, staging_path_filename)
            else:
                with staging_path_filename.open("wb") as f:
                    self.install_context.fetch_to(url, f)
            self._logger.info("%s -> %s", url, filename)
        self.install_context.stage_command(staging, ["bash", "-c", self.script])
        if self.strip:
            self.install_context.strip_exes(staging, self.strip)

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
            if self.install_path_symlink:
                self.install_context.set_link(Path(self.install_path), self.install_path_symlink)

    def __repr__(self) -> str:
        return f"ScriptInstallable({self.name}, {self.install_path})"
