from __future__ import annotations

import re
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

from lib.installable.installable import Installable
from lib.installation_context import InstallationContext
from lib.staging import StagingDir


def is_virtualenv(path: Path) -> bool:
    """Check if the path is a Python virtualenv"""
    return path.is_dir() and (path / "bin" / "activate").is_file()


def find_and_replace_paths(dest_path: Path, source_path: Path) -> None:
    """Replace old virtualenv paths with new paths in all relevant files"""
    # Find and replace old virtualenv path with new
    bin_files: list[Path]
    record_files: list[Path]

    # Find files in bin directory
    bin_dir = dest_path / "bin"
    bin_files = list(bin_dir.glob("**/*"))
    bin_files = [f for f in bin_files if f.is_file()]

    # Find RECORD files in lib directory
    lib_dir = dest_path / "lib"
    record_files = list(lib_dir.glob("**/RECORD"))

    source_path_bytes = bytes(str(source_path), "ascii")
    dest_path_bytes = bytes(str(dest_path), "ascii")

    # Check all files for the source path
    files_to_modify: list[Path] = []
    for file_path in bin_files + record_files:
        content = file_path.read_bytes()
        if source_path_bytes in content:
            files_to_modify.append(file_path)

    # Replace the source path with destination path in all files
    for file_path in files_to_modify:
        content = file_path.read_bytes()
        # Replace the path
        content = content.replace(source_path_bytes, dest_path_bytes)
        file_path.write_bytes(content)


def update_activation_scripts(dest_path: Path) -> None:
    """Update the virtualenv activation scripts with the new name"""
    venv_name = dest_path.name

    # Update activate script
    activate_file = dest_path / "bin" / "activate"
    if activate_file.exists():
        content = activate_file.read_text()
        # Replace PS1 prompts
        content = re.sub(r'if \[ "x\(\S+\) " != x ] ; then', f'if [ "x({venv_name}) " != x ] ; then', content)
        content = re.sub(r'PS1="\(\S+\) \$PS1"', f'PS1="({venv_name}) $PS1"', content)
        activate_file.write_text(content)

    # Update activate.csh if it exists
    csh_file = dest_path / "bin" / "activate.csh"
    if csh_file.exists():
        content = csh_file.read_text()
        content = re.sub(r'if \("\S+" != ""\) then', f'if ("{venv_name}" != "") then', content)
        content = re.sub(r'set env_name = "\S+"', f'set env_name = "{venv_name}"', content)
        csh_file.write_text(content)

    # Update activate.fish if it exists
    fish_file = dest_path / "bin" / "activate.fish"
    if fish_file.exists():
        content = fish_file.read_text()
        content = re.sub(r'if test -n "(\$\?)?\\(\S+\\) "', f'if test -n "\\\\1({venv_name}) "', content)
        content = re.sub(
            r'printf "%s%s%s" "(\$\?)?\\(\S+\\) " \\(set_color normal\\) \\(_old_fish_prompt\\)',
            f'printf "%s%s%s" "\\\\1({venv_name}) " (set_color normal) (_old_fish_prompt)',
            content,
        )
        fish_file.write_text(content)


def fix_pth_files(dest_path: Path, source_path: Path, dest_path_str: str) -> None:
    """Fix absolute paths in .pth files"""
    source_path_str = str(source_path)
    if not source_path_str.endswith("/"):
        source_path_str += "/"

    # Find all .pth files in site-packages directories
    pth_files = []
    for path in dest_path.rglob("*.pth"):
        if "site-packages" in str(path.parent):
            pth_files.append(path)

    for file_path in pth_files:
        try:
            content = file_path.read_text()
            # Replace the path
            content = content.replace(source_path_str, dest_path_str + "/")
            file_path.write_text(content)
        except (OSError, UnicodeDecodeError):
            continue


def fix_symlinks(dest_path: Path) -> None:
    """Fix dangling symlinks in the local directory"""
    local_dir = dest_path / "local"
    if not local_dir.is_dir():
        return

    # Find all files recursively
    for path in local_dir.rglob("*"):
        if path.is_symlink():
            link_target = path.readlink()
            if "local/" in str(link_target):
                # Remove local/ from the path
                new_target = str(link_target).replace("local/", "")
                # Remove the old link and create a new one
                path.unlink()
                path.symlink_to(new_target)


def do_mv(source: str | Path, dest: str | Path) -> None:
    """Move a Python virtualenv from source to dest, updating all references"""
    dest_path = Path(dest).absolute()
    source_path = Path(source).absolute()

    # Move directory
    shutil.move(str(source_path), str(dest_path))

    # Ensure move was successful
    if not is_virtualenv(dest_path):
        raise RuntimeError(f"failed to move '{source_path}' to '{dest_path}'", str(source_path), str(dest_path))

    # Fix paths in all files
    find_and_replace_paths(dest_path, source_path)

    # Fix paths in venv activation scripts
    if (dest_path / "pyvenv.cfg").is_file():
        update_activation_scripts(dest_path)

    # Fix paths in .pth files
    fix_pth_files(dest_path, source_path, str(dest_path))

    # Fix symlinks
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
            self.install_context.move_from_staging(staging, self.name, self.install_path, do_staging_move=do_mv)

    def resolve_dependencies(self, resolver: Callable[[str], str]) -> None:
        self.python = resolver(self.python)

    def __repr__(self) -> str:
        return f"PipInstallable({self.name}, {self.install_path})"
