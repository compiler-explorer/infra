from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

from lib.installable.installable import Installable
from lib.installation_context import InstallationContext
from lib.staging import StagingDir


class ScriptInstallable(Installable):
    def __init__(self, install_context: InstallationContext, config: dict[str, Any]):
        super().__init__(install_context, config)
        self.install_path = self.config_get("dir")
        self.install_path_symlink = self.config_get("symlink", False)
        self.fetch = self.config_get("fetch", [])
        self.script = self.config_get("script")
        self.strip = self.config_get("strip", False)

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
        cmd = ["bash", "-c", self.script]
        if self.install_context.cefs_enabled:
            # Use bubblewrap to ensure a "real" path for every dependency and nothing else.
            # That way we can avoid any issues with symlinks in CEFS mounts.
            binds = []
            for dep in self.depends:
                dep_path = Path(self.install_context.destination / dep.install_path)
                binds += ["--bind", str(dep_path.resolve()), str(dep_path)]
            cmd = ["bwrap", "--dev-bind", "/", "/", "--tmpfs", str(self.install_context.destination)] + binds + cmd
        self.install_context.stage_command(staging, cmd)
        if self.strip:
            self.install_context.strip_exes(staging, self.strip)

    def resolve_dependencies(self, resolver: Callable[[str], str]) -> None:
        self.script = resolver(self.script)

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
            if self.install_path_symlink:
                self.install_context.set_link(Path(self.install_path), self.install_path_symlink)

    def __repr__(self) -> str:
        return f"ScriptInstallable({self.name}, {self.install_path})"
