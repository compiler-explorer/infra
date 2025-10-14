from __future__ import annotations

import shutil
from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import Any

from lib.installable.installable import Installable
from lib.installation_context import InstallationContext
from lib.staging import StagingDir


def relocate_script_paths(source: str | Path, dest: str | Path, dirs: list[str]) -> None:
    """
    Relocate paths in script-installed files from staging to final destination.

    Performs byte-level replacement of staging path with destination path in files
    within specified subdirectories. Only processes regular files, not symlinks.

    Args:
        source: Staging directory path
        dest: Final destination path
        dirs: List of subdirectories to process (e.g., ["bin", "libexec"])
    """
    source_path = Path(source).absolute()
    dest_path = Path(dest).absolute()

    source_path_bytes = bytes(str(source_path), "utf-8")
    dest_path_bytes = bytes(str(dest_path), "utf-8")

    for dir_name in dirs:
        target_dir = source_path / dir_name
        if not target_dir.exists():
            continue

        for file_path in target_dir.iterdir():
            if file_path.is_file() and not file_path.is_symlink():
                content = file_path.read_bytes()
                if source_path_bytes in content:
                    content = content.replace(source_path_bytes, dest_path_bytes)
                    file_path.write_bytes(content)


class ScriptInstallable(Installable):
    def __init__(self, install_context: InstallationContext, config: dict[str, Any]):
        super().__init__(install_context, config)
        self.install_path = self.config_get("dir")
        self.install_path_symlink = self.config_get("symlink", False)
        self.fetch = self.config_get("fetch", [])
        self.script = self.config_get("script")
        self.strip = self.config_get("strip", False)
        self.relocate_paths = self.config_get("relocate_paths", [])

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
            relocate = None
            if self.relocate_paths:
                relocate = partial(relocate_script_paths, dirs=self.relocate_paths)
            self.install_context.move_from_staging(staging, self.name, self.install_path, relocate=relocate)
            if self.install_path_symlink:
                self.install_context.set_link(Path(self.install_path), self.install_path_symlink)

    def __repr__(self) -> str:
        return f"ScriptInstallable({self.name}, {self.install_path})"
