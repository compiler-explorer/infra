from __future__ import annotations

import contextlib
import glob
import logging
import os
import shlex
import shutil
import stat
import subprocess
import tempfile
import time
import uuid
from collections.abc import Callable, Collection, Iterator, Sequence
from pathlib import Path
from typing import IO

import requests
import requests.adapters
import requests_cache
import yaml

from lib.cefs.deployment import backup_and_symlink, deploy_to_cefs_transactional
from lib.cefs.paths import get_cefs_filename_for_image, get_cefs_paths
from lib.cefs_manifest import (
    create_installable_manifest_entry,
    create_manifest,
)
from lib.config import Config
from lib.config_safe_loader import ConfigSafeLoader
from lib.library_platform import LibraryPlatform
from lib.squashfs import create_squashfs_image
from lib.staging import StagingDir

_LOGGER = logging.getLogger(__name__)
PathOrString = Path | str


def is_windows():
    return os.name == "nt"


def fix_single_permission(file_path: Path) -> None:
    """Fix permissions for a single file or directory.

    Mirrors user permissions to group and other, but never grants write to group/other.
    Always ensures user has write permission for future editing.
    """
    # Skip symlinks - they don't have their own permissions and
    # chmod would affect the target, which may not exist (broken symlinks)
    if file_path.is_symlink():
        return

    current_mode = file_path.stat().st_mode
    current_perms = stat.S_IMODE(current_mode)

    # Build expected permissions:
    # - User always gets write, keeps read/exec
    # - Group/other mirror user's read/exec but never get write
    new_perms = (current_perms & stat.S_IRWXU) | stat.S_IWUSR  # Always give user write

    if bool(current_perms & stat.S_IRUSR):
        new_perms |= stat.S_IRGRP
        new_perms |= stat.S_IROTH
    if bool(current_perms & stat.S_IXUSR):
        new_perms |= stat.S_IXGRP
        new_perms |= stat.S_IXOTH

    if current_perms != new_perms:
        _LOGGER.debug("Fixing permissions on %s: %s -> %s", file_path, oct(current_perms), oct(new_perms))
        file_path.chmod(new_perms)


def fix_permissions(path: Path) -> None:
    """Fix permissions recursively to ensure files are accessible by all users.

    Mirrors user permissions to group and other, but never grants write to group/other.
    Always ensures user has write permission for future editing.
    """
    # Fix the root directory itself first
    fix_single_permission(path)

    # Then fix all subdirectories and files
    for root, dirs, files in os.walk(path):
        for dir_name in dirs:
            dir_path = Path(root) / dir_name
            fix_single_permission(dir_path)

        for file_name in files:
            file_path = Path(root) / file_name
            fix_single_permission(file_path)


class FetchFailure(RuntimeError):
    pass


class PostFailure(RuntimeError):
    pass


class InstallationContext:
    def __init__(
        self,
        destination: Path,
        staging_root: Path,
        s3_url: str,
        dry_run: bool,
        is_nightly_enabled: bool,
        only_nightly: bool,
        cache: Path | None,
        yaml_dir: Path,
        allow_unsafe_ssl: bool,
        resource_dir: Path,
        keep_staging: bool,
        check_user: str,
        platform: LibraryPlatform,
        config: Config,
    ):
        self._destination = destination
        self._prior_installation = self.destination
        self._staging_root = staging_root
        self._keep_staging = keep_staging
        self.config = config
        self.s3_url = s3_url
        self.dry_run = dry_run
        self.is_nightly_enabled = is_nightly_enabled
        self.only_nightly = only_nightly
        self.platform = platform
        retry_strategy = requests.adapters.Retry(
            total=10,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS"],
        )
        self.allow_unsafe_ssl = allow_unsafe_ssl
        adapter = requests.adapters.HTTPAdapter(max_retries=retry_strategy)
        if cache:
            _LOGGER.debug("Using cache %s", cache)
            self.fetcher = requests_cache.CachedSession(cache)
        else:
            _LOGGER.debug("Making uncached requests")
            self.fetcher = requests.Session()
        self.fetcher.mount("https://", adapter)
        self.fetcher.mount("http://", adapter)
        self.yaml_dir = yaml_dir
        self.resource_dir = resource_dir
        self.run_checks_as_user = check_user

    @property
    def destination(self) -> Path:
        return self._destination

    @property
    def prior_installation(self) -> Path:
        return self._prior_installation

    @property
    def cefs_enabled(self) -> bool:
        return self.config.cefs.enabled

    @contextlib.contextmanager
    def new_staging_dir(self) -> Iterator[StagingDir]:
        # Use local staging directory when CEFS is enabled for better performance
        if self.cefs_enabled:
            local_staging_root = self.config.cefs.local_temp_dir / "staging"
            local_staging_root.mkdir(parents=True, exist_ok=True)
            staging_dir = StagingDir(local_staging_root / str(uuid.uuid4()), self._keep_staging)
        else:
            staging_dir = StagingDir(self._staging_root / str(uuid.uuid4()), self._keep_staging)
        try:
            yield staging_dir
        finally:
            if not self._keep_staging:
                if staging_dir.path.is_dir() and not is_windows():
                    subprocess.check_call(["chmod", "-R", "u+w", staging_dir.path])
                shutil.rmtree(staging_dir.path, ignore_errors=True)

    def fetch_rest_query(self, url: str) -> dict:
        _LOGGER.debug("Fetching %s", url)
        return yaml.load(self.fetcher.get(url).text, Loader=ConfigSafeLoader)

    def fetch_to(self, url: str, fd: IO[bytes], agent: str = "") -> None:
        _LOGGER.debug("Fetching %s", url)

        if agent:
            headers = {"User-Agent": agent}

            if self.allow_unsafe_ssl:
                request = self.fetcher.get(url, stream=True, verify=False, allow_redirects=True, headers=headers)
            else:
                request = self.fetcher.get(url, stream=True, allow_redirects=True, headers=headers)
        else:
            if self.allow_unsafe_ssl:
                request = self.fetcher.get(url, stream=True, verify=False, allow_redirects=True)
            else:
                request = self.fetcher.get(url, stream=True, allow_redirects=True)

        if not request.ok:
            _LOGGER.error("Failed to fetch %s: %s", url, request)
            raise FetchFailure(f"Fetch failure for {url}: {request}")
        fetched = 0
        length = int(request.headers.get("content-length", 0))
        _LOGGER.info("Fetching %s (%d bytes)", url, length)
        report_every_secs = 5
        report_time = time.time() + report_every_secs
        for chunk in request.iter_content(chunk_size=4 * 1024 * 1024):
            fd.write(chunk)
            fetched += len(chunk)
            now = time.time()
            if now >= report_time:
                if length != 0:
                    _LOGGER.info("%.1f%% of %s...", 100.0 * fetched / length, url)
                report_time = now + report_every_secs
        _LOGGER.info("100%% of %s", url)
        fd.flush()

    def fetch_url_and_pipe_to(
        self, staging: StagingDir, url: str, command: Sequence[str], subdir: Path | str = ".", agent: str = ""
    ) -> None:
        untar_dir = staging.path / subdir
        untar_dir.mkdir(parents=True, exist_ok=True)

        if is_windows() and command[0] == "7z":
            temp_file_path = ""

            # download the file first
            with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                temp_file_path = temp_file.name
                self.fetch_to(url, temp_file, agent)

            # create a powershell script to extract the file
            with tempfile.NamedTemporaryFile(suffix=".ps1", delete=False) as script_file:
                # first to extract the tar file
                script_file.write(
                    f'{" ".join(command)} -o"{os.path.dirname(temp_file_path)}" {temp_file_path}\n'.encode()
                )
                # the tar file was automatically suffixed with ~ by 7z, extract that tar to the untar_dir
                script_file.write(f'7z x -ttar -o"{untar_dir}" {temp_file_path}~\n'.encode())

            subprocess.check_call(["pwsh", script_file.name], cwd=str(untar_dir))

            os.remove(temp_file_path + "~")
            os.remove(temp_file_path)
            os.remove(script_file.name)
        else:
            # We stream to a temporary file first before then piping this to the command
            # as sometimes the command can take so long the URL endpoint closes the door on us
            with tempfile.TemporaryFile() as fd:
                self.fetch_to(url, fd, agent)
                fd.seek(0)
                _LOGGER.info("Piping to %s", shlex.join(command))
                subprocess.check_call(command, stdin=fd, cwd=str(untar_dir))

    def stage_command(self, staging: StagingDir, command: Sequence[str], cwd: Path | None = None) -> None:
        _LOGGER.info("Staging with %s", shlex.join(command))
        env = os.environ.copy()
        env["CE_STAGING_DIR"] = str(staging.path)
        subprocess.check_call(command, cwd=str(cwd or staging.path), env=env)

    def fetch_s3_and_pipe_to(self, staging: StagingDir, s3: str, command: Sequence[str]) -> None:
        return self.fetch_url_and_pipe_to(staging, f"{self.s3_url}/{s3}", command)

    def stage_subdir(self, staging: StagingDir, subdir: str) -> None:
        (staging.path / subdir).mkdir(parents=True, exist_ok=True)

    def make_subdir(self, subdir: str) -> None:
        (self.destination / subdir).mkdir(parents=True, exist_ok=True)

    def get_current_link_target(self, dest: str) -> Path:
        full_dest = self.destination / dest
        if full_dest.is_symlink():
            return full_dest.readlink()
        else:
            return full_dest

    def set_link(self, source: Path, dest: str) -> None:
        if self.dry_run:
            _LOGGER.info("Would symlink %s to %s", source, dest)
            return

        full_source = self.destination / source
        if not full_source.exists():
            raise RuntimeError(f"During symlinking, {full_source} was not present")
        full_dest = self.destination / dest
        _LOGGER.debug("Checking whether Symlink %s exists", full_dest)
        if full_dest.is_symlink():
            _LOGGER.debug("Symlink does exist, unlinking...")
            full_dest.unlink()
            _LOGGER.debug("Symlink should be unlinked")
        relative_source = full_source.relative_to(Path(os.path.commonpath([full_source, full_dest])))
        _LOGGER.info("Symlinking %s to %s", relative_source, full_dest)
        full_dest.symlink_to(relative_source)

    def glob(self, pattern: str) -> Collection[str]:
        return [os.path.relpath(x, str(self.destination)) for x in glob.glob(str(self.destination / pattern))]

    def remove_dir(self, directory: str | Path) -> None:
        if self.dry_run:
            _LOGGER.info("Would remove directory %s but in dry-run mode", directory)
        else:
            shutil.rmtree(str(self.destination / directory), ignore_errors=True)
            _LOGGER.info("Removing %s", directory)

    def check_link(self, source: str, link: str) -> bool:
        _LOGGER.debug("check link %s", link)
        try:
            link_dest = (self.destination / link).resolve(strict=True)
            full_source = (self.destination / source).resolve(strict=True)
            _LOGGER.debug("resolving link returned %s, comparing to %s", link_dest, full_source)
            return full_source == link_dest
        except FileNotFoundError:
            _LOGGER.debug("File not found for %s", link)
            return False

    def move_from_staging(
        self,
        staging: StagingDir,
        installable_name: str,
        source: PathOrString,
        dest: PathOrString | None = None,
        relocate: Callable[[Path, Path], None] | None = None,
    ) -> None:
        dest = dest or source

        if self.dry_run:
            _LOGGER.info("Would install %s to %s but in dry-run mode", source, dest)
            return

        # Check if CEFS is enabled and should be used for this installation
        if self.cefs_enabled:
            _LOGGER.info("Installing via CEFS: %s -> %s", source, dest)
            self._deploy_to_cefs(staging, installable_name, source, dest, relocate=relocate)
            return

        # Traditional installation flow
        existing_dir_rename = staging.path.with_suffix(".orig")
        source_path = staging.path / source
        dest_path = self.destination / dest

        dest_path.parent.mkdir(parents=True, exist_ok=True)
        _LOGGER.info("Moving from staging (%s) to final destination (%s)", source_path, dest_path)

        if not source_path.is_dir():
            staging_contents = subprocess.check_output(["ls", "-l", str(staging.path)]).decode("utf-8")
            _LOGGER.info("Directory listing of staging:\n%s", staging_contents)
            raise RuntimeError(f"Missing source '{source_path}'")

        # Fix permissions to ensure files are accessible by all users
        if not is_windows():
            fix_permissions(source_path)

        state = ""
        if dest_path.is_dir():
            if list(dest_path.iterdir()):
                _LOGGER.info(
                    "Destination %s exists, temporarily moving out of the way (to %s)", dest_path, existing_dir_rename
                )
                dest_path.replace(existing_dir_rename)
                state = "old_renamed"
            else:
                _LOGGER.info("Destination %s exists but is empty; deleting it", dest_path)
                shutil.rmtree(dest_path)

        try:
            if relocate:
                relocate(source_path, dest_path)
            source_path.replace(dest_path)
            if state == "old_renamed":
                state = "old_needs_remove"
        finally:
            if state == "old_needs_remove":
                _LOGGER.info("Removing temporarily moved %s", existing_dir_rename)
                shutil.rmtree(existing_dir_rename, ignore_errors=True)
            elif state == "old_renamed":
                _LOGGER.warning("Moving old destination back")
                existing_dir_rename.replace(dest_path)

    def compare_against_staging(self, staging: StagingDir, source_str: str, dest_str: str | None = None) -> bool:
        dest_str = dest_str or source_str
        source = staging.path / source_str
        dest = self.destination / dest_str
        _LOGGER.info("Comparing %s vs %s...", source, dest)
        result = subprocess.call(["diff", "-r", source, dest])
        if result == 0:
            _LOGGER.info("Contents match")
        else:
            _LOGGER.warning("Contents differ")
        return result == 0

    def check_output(self, args: list[str], env: dict | None = None, stderr_on_stdout=False) -> str:
        args = args[:]
        args[0] = str(self.destination / args[0])
        _LOGGER.debug("Executing %s in %s", args, self.destination)
        if not is_windows():
            output = subprocess.run(
                args,
                cwd=str(self.destination),
                env=env,
                stdin=subprocess.DEVNULL,
                stderr=subprocess.STDOUT if stderr_on_stdout else None,
                stdout=subprocess.PIPE,
                check=True,
            )
        else:
            output = subprocess.run(
                args,
                cwd=str(self.destination),
                stdin=subprocess.DEVNULL,
                stderr=subprocess.STDOUT if stderr_on_stdout else None,
                stdout=subprocess.PIPE,
                check=True,
            )

        fulloutput = ""
        if output.stdout is not None:
            fulloutput += output.stdout.decode("utf-8")
        if output.stderr is not None:
            fulloutput += output.stderr.decode("utf-8")

        return fulloutput

    def check_call(self, args: list[str], env: dict | None = None) -> None:
        args = args[:]
        args[0] = str(self.destination / args[0])
        _LOGGER.debug("Executing %s in %s", args, self.destination)
        subprocess.check_call(args, cwd=str(self.destination), env=env, stdin=subprocess.DEVNULL)

    def strip_exes(self, staging: StagingDir, paths: bool | list[str]) -> None:
        if isinstance(paths, bool):
            if not paths:
                return
            paths = ["."]
        to_strip = []
        for path_part in paths:
            path = staging.path / path_part
            _LOGGER.debug("Looking for executables to strip in %s", path)
            if not path.is_dir():
                raise RuntimeError(f"While looking for files to strip, {path} was not a directory")
            for dirpath, _, filenames in os.walk(str(path)):
                for filename in filenames:
                    full_path = os.path.join(dirpath, filename)
                    if os.access(full_path, os.X_OK):
                        to_strip.append(full_path)

        # Deliberately ignore errors
        subprocess.call(["strip"] + to_strip)

    def run_script(self, staging: StagingDir, from_path: str | Path, lines: list[str]) -> None:
        from_path = Path(from_path)
        if len(lines) > 0:
            _LOGGER.info("Running script")
            if self.platform == LibraryPlatform.Linux:
                script_file = from_path / "ce_script.sh"
                with script_file.open("w", encoding="utf-8") as f:
                    f.write("#!/bin/bash\n\nset -euo pipefail\n\n")
                    for line in lines:
                        f.write(f"{line}\n")

                script_file.chmod(0o755)
                self.stage_command(staging, [str(script_file)], cwd=from_path)
                if not self.dry_run:
                    script_file.unlink()
            elif self.platform == LibraryPlatform.Windows:
                script_file = from_path / "ce_script.ps1"
                with script_file.open("w", encoding="utf-8") as f:
                    for line in lines:
                        f.write(f"{line}\n")
                self.stage_command(staging, ["pwsh", str(script_file)], cwd=from_path)
                if not self.dry_run:
                    script_file.unlink()

    def is_elf(self, maybe_elf_file: Path):
        return b"ELF" in subprocess.check_output(["file", maybe_elf_file])

    def _deploy_to_cefs(
        self,
        staging: StagingDir,
        installable_name: str,
        source: PathOrString,
        dest: PathOrString,
        relocate: Callable[[Path, Path], None] | None,
    ) -> None:
        """Deploy staging content directly to CEFS storage."""
        if not self.config.cefs.enabled:
            raise RuntimeError("CEFS not enabled but _deploy_to_cefs called")

        source_path = staging.path / source
        if not source_path.is_dir():
            raise RuntimeError(f"Missing source '{source_path}'")

        nfs_path = self.destination / dest
        if relocate:
            relocate(source_path, nfs_path)

        # Fix permissions before squashing
        if not is_windows():
            fix_permissions(source_path)

        installable_info = create_installable_manifest_entry(installable_name, nfs_path)
        manifest = create_manifest(
            operation="install",
            description=f"Created through installation of {installable_name}",
            contents=[installable_info],
        )

        # Create temporary squashfs image
        temp_squash_file = self.config.cefs.local_temp_dir / f"temp_{uuid.uuid4()}.img"

        # Create squashfs image from processed content
        _LOGGER.info("Creating squashfs image from %s", source_path)
        try:
            create_squashfs_image(self.config.squashfs, source_path, temp_squash_file)

            filename = get_cefs_filename_for_image(temp_squash_file, "install", Path(dest))
            cefs_paths = get_cefs_paths(self.config.cefs.image_dir, self.config.cefs.mount_point, filename)

            if cefs_paths.image_path.exists():
                _LOGGER.info("CEFS image already exists: %s", cefs_paths.image_path)
                backup_and_symlink(nfs_path, cefs_paths.mount_path, self.dry_run, defer_cleanup=False)
            else:
                _LOGGER.info("Copying squashfs to CEFS storage: %s", cefs_paths.image_path)
                with deploy_to_cefs_transactional(temp_squash_file, cefs_paths.image_path, manifest, self.dry_run):
                    # TODO: Add defer_cleanup parameter to install command to speed up bulk installations
                    backup_and_symlink(nfs_path, cefs_paths.mount_path, self.dry_run, defer_cleanup=False)
        finally:
            if temp_squash_file.exists():
                temp_squash_file.unlink()
