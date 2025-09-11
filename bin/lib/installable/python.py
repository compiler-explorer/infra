from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from lib.installable.installable import Installable
from lib.installation_context import InstallationContext
from lib.staging import StagingDir


def find_and_replace_paths(dest_path: Path, source_path: Path) -> None:
    """Replace old virtualenv paths with new paths in all relevant files"""
    # Find and replace old virtualenv path with new
    bin_files: list[Path]
    record_files: list[Path]

    top_level_files = [f for f in source_path.glob("*") if f.is_file()]
    bin_files = [f for f in (source_path / "bin").glob("**/*") if f.is_file()]
    record_files = list((source_path / "lib").glob("**/RECORD"))

    source_path_bytes = bytes(str(source_path), "ascii")
    dest_path_bytes = bytes(str(dest_path), "ascii")

    for file_path in top_level_files + bin_files + record_files:
        if source_path_bytes in (content := file_path.read_bytes()):
            content = content.replace(source_path_bytes, dest_path_bytes)
            file_path.write_bytes(content)


def update_activation_scripts(dest_path: Path, source_path: Path) -> None:
    """Update the virtualenv activation scripts with the new name"""
    venv_name = dest_path.name

    activate_file = source_path / "bin" / "activate"
    if activate_file.exists():
        content = activate_file.read_text()
        content = re.sub(
            r'if \[ "x\(\S+\) " != x ] ; then',
            f'if [ "x({venv_name}) " != x ] ; then',
            content,
        )
        content = re.sub(r'PS1="\(\S+\) \$PS1"', f'PS1="({venv_name}) $PS1"', content)
        activate_file.write_text(content)


def fix_pth_files(dest_path: Path, source_path: Path) -> None:
    """Fix absolute paths in .pth files"""

    # Find all .pth files in site-packages directories
    for path in source_path.rglob("*.pth"):
        if "site-packages" in path.parent.parts:
            try:
                content = path.read_text()
                content = content.replace(f"{source_path}/", f"{dest_path}/")
                path.write_text(content)
            except (OSError, UnicodeDecodeError):
                continue


def fix_symlinks(env_root: Path) -> None:
    """Fix dangling symlinks in the local directory"""
    local_dir = env_root / "local"
    if not local_dir.is_dir():
        return

    for path in local_dir.rglob("*"):
        if path.is_symlink():
            link_target = path.readlink()
            if "local/" in str(link_target):
                # Remove local/ from the path
                new_target = str(link_target).replace("local/", "")
                # Remove the old link and create a new one
                path.unlink()
                path.symlink_to(new_target)


def do_relocate(source: str | Path, dest: str | Path) -> None:
    """
    Relocate a Python virtual environment from source to dest.

    Updates source as if it was going to be actually used and run from dest.
    """
    dest_path = Path(dest).absolute()
    source_path = Path(source).absolute()

    find_and_replace_paths(dest_path, source_path)
    if (source_path / "pyvenv.cfg").is_file():
        update_activation_scripts(dest_path, source_path)

    fix_pth_files(dest_path, source_path)
    fix_symlinks(dest_path)


class PipInstallable(Installable):
    def __init__(self, install_context: InstallationContext, config: dict[str, Any]):
        super().__init__(install_context, config)
        self.install_path: str = self.config_get("dir")
        self.package: str | list[str] = self.config_get("package")
        self.python: str = self.config_get("python")

    def stage(self, staging: StagingDir) -> None:
        venv = staging.path / self.install_path
        self.install_context.check_output([self.python, "-mvenv", str(venv)])
        packages = self.package
        if isinstance(packages, str):
            packages = [packages]
        self.install_context.check_output([str(venv / "bin" / "pip"), "--no-cache-dir", "install", *packages])

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
            self.install_context.move_from_staging(staging, self.name, self.install_path, relocate=do_relocate)

    def resolve_dependencies(self, resolver: Callable[[str], str]) -> None:
        self.python = resolver(self.python)

    def __repr__(self) -> str:
        return f"PipInstallable({self.name}, {self.install_path})"
