from __future__ import annotations

import contextlib
import functools
import glob
import json
import logging
import os
import re
import shlex
import shutil
import subprocess
import tempfile
import time
import uuid
from collections import defaultdict, ChainMap
from datetime import datetime, timedelta
from functools import partial
from pathlib import Path
from typing import Optional, Sequence, Collection, List, Union, Dict, Any, IO, Callable, Iterator

import requests
import requests.adapters
import yaml
from cachecontrol import CacheControl
from cachecontrol.caches import FileCache

from lib.amazon import list_compilers, list_s3_artifacts
from lib.config_expand import is_value_type, expand_target
from lib.config_safe_loader import ConfigSafeLoader
from lib.library_build_config import LibraryBuildConfig
from lib.library_builder import LibraryBuilder
from lib.rust_library_builder import RustLibraryBuilder
from lib.staging import StagingDir

VERSIONED_RE = re.compile(r"^(.*)-([0-9.]+)$")
NO_DEFAULT = "__no_default__"

_LOGGER = logging.getLogger(__name__)


class FetchFailure(RuntimeError):
    pass


@functools.lru_cache(maxsize=1)
def s3_available_compilers():
    compilers = defaultdict(lambda: [])
    for compiler in list_compilers():
        match = VERSIONED_RE.match(compiler)
        if match:
            compilers[match.group(1)].append(match.group(2))
    return compilers


class InstallationContext:
    def __init__(
        self,
        destination: Path,
        staging_root: Path,
        s3_url: str,
        dry_run: bool,
        is_nightly_enabled: bool,
        cache: Optional[Path],
        yaml_dir: Path,
        allow_unsafe_ssl: bool,
        resource_dir: Path,
        keep_staging: bool,
    ):
        self.destination = destination
        self._staging_root = staging_root
        self._keep_staging = keep_staging
        self.s3_url = s3_url
        self.dry_run = dry_run
        self.is_nightly_enabled = is_nightly_enabled
        retry_strategy = requests.adapters.Retry(
            total=10,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            method_whitelist=["HEAD", "GET", "OPTIONS"],
        )
        self.allow_unsafe_ssl = allow_unsafe_ssl
        adapter = requests.adapters.HTTPAdapter(max_retries=retry_strategy)
        http = requests.Session()
        http.mount("https://", adapter)
        http.mount("http://", adapter)
        if cache:
            _LOGGER.info("Using cache %s", cache)
            self.fetcher = CacheControl(http, cache=FileCache(cache))
        else:
            _LOGGER.info("Making uncached requests")
            self.fetcher = http
        self.yaml_dir = yaml_dir
        self.resource_dir = resource_dir

    @contextlib.contextmanager
    def new_staging_dir(self) -> Iterator[StagingDir]:
        staging_dir = StagingDir(self._staging_root / str(uuid.uuid4()), self._keep_staging)
        try:
            yield staging_dir
        finally:
            if not self._keep_staging:
                if staging_dir.path.is_dir():
                    subprocess.check_call(["chmod", "-R", "u+w", staging_dir.path])
                shutil.rmtree(staging_dir.path, ignore_errors=True)

    def fetch_rest_query(self, url: str) -> Dict:
        _LOGGER.debug("Fetching %s", url)
        return yaml.load(self.fetcher.get(url).text, Loader=ConfigSafeLoader)

    def fetch_to(self, url: str, fd: IO[bytes]) -> None:
        _LOGGER.debug("Fetching %s", url)
        if self.allow_unsafe_ssl:
            request = self.fetcher.get(url, stream=True, verify=False)
        else:
            request = self.fetcher.get(url, stream=True)

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
                    _LOGGER.info("%.1f of %s...", 100.0 * fetched / length, url)
                report_time = now + report_every_secs
        _LOGGER.info("100%% of %s", url)
        fd.flush()

    def fetch_url_and_pipe_to(
        self, staging: StagingDir, url: str, command: Sequence[str], subdir: Union[Path, str] = "."
    ) -> None:
        untar_dir = staging.path / subdir
        untar_dir.mkdir(parents=True, exist_ok=True)
        # We stream to a temporary file first before then piping this to the command
        # as sometimes the command can take so long the URL endpoint closes the door on us
        with tempfile.TemporaryFile() as fd:
            self.fetch_to(url, fd)
            fd.seek(0)
            _LOGGER.info("Piping to %s", shlex.join(command))
            subprocess.check_call(command, stdin=fd, cwd=str(untar_dir))

    def stage_command(self, staging: StagingDir, command: Sequence[str], cwd: Optional[Path] = None) -> None:
        _LOGGER.info("Staging with %s", shlex.join(command))
        env = os.environ.copy()
        env["CE_STAGING_DIR"] = str(staging.path)
        subprocess.check_call(command, cwd=str(cwd or staging.path), env=env)

    def fetch_s3_and_pipe_to(self, staging: StagingDir, s3: str, command: Sequence[str]) -> None:
        return self.fetch_url_and_pipe_to(staging, f"{self.s3_url}/{s3}", command)

    def make_subdir(self, subdir: str) -> None:
        (self.destination / subdir).mkdir(parents=True, exist_ok=True)

    def read_link(self, link: str) -> str:
        return os.readlink(str(self.destination / link))

    def set_link(self, source: Path, dest: str) -> None:
        if self.dry_run:
            _LOGGER.info("Would symlink %s to %s", source, dest)
            return

        full_dest = self.destination / dest
        if full_dest.exists():
            full_dest.unlink()
        _LOGGER.info("Symlinking %s to %s", source, full_dest)
        os.symlink(str(source), str(full_dest))

    def glob(self, pattern: str) -> Collection[str]:
        return [os.path.relpath(x, str(self.destination)) for x in glob.glob(str(self.destination / pattern))]

    def remove_dir(self, directory: Union[str, Path]) -> None:
        if self.dry_run:
            _LOGGER.info("Would remove directory %s but in dry-run mode", directory)
        else:
            shutil.rmtree(str(self.destination / directory), ignore_errors=True)
            _LOGGER.info("Removing %s", directory)

    def check_link(self, source: str, link: str) -> bool:
        try:
            link = self.read_link(link)
            _LOGGER.debug("readlink returned %s", link)
            return link == source
        except FileNotFoundError:
            _LOGGER.debug("File not found for %s", link)
            return False

    def move_from_staging(
        self,
        staging: StagingDir,
        source_str: str,
        dest_str: Optional[str] = None,
        do_staging_move=lambda source, dest: source.replace(dest),
    ) -> None:
        dest_str = dest_str or source_str
        existing_dir_rename = staging.path / "temp_orig"
        source = staging.path / source_str
        dest = self.destination / dest_str
        if self.dry_run:
            _LOGGER.info("Would install %s to %s but in dry-run mode", source, dest)
            return
        dest.parent.mkdir(parents=True, exist_ok=True)
        _LOGGER.info("Moving from staging (%s) to final destination (%s)", source, dest)
        if not source.is_dir():
            staging_contents = subprocess.check_output(["ls", "-l", str(staging.path)]).decode("utf-8")
            _LOGGER.info("Directory listing of staging:\n%s", staging_contents)
            raise RuntimeError(f"Missing source '{source}'")
        # Some tar'd up GCCs are actually marked read-only...
        subprocess.check_call(["chmod", "-R", "u+w", source])
        state = ""
        if dest.is_dir():
            _LOGGER.info("Destination %s exists, temporarily moving out of the way (to %s)", dest, existing_dir_rename)
            dest.replace(existing_dir_rename)
            state = "old_renamed"
        try:
            do_staging_move(source, dest)
            if state == "old_renamed":
                state = "old_needs_remove"
        finally:
            if state == "old_needs_remove":
                _LOGGER.debug("Removing temporarily moved %s", existing_dir_rename)
                shutil.rmtree(existing_dir_rename, ignore_errors=True)
            elif state == "old_renamed":
                _LOGGER.warning("Moving old destination back")
                existing_dir_rename.replace(dest)

    def compare_against_staging(self, staging: StagingDir, source_str: str, dest_str: Optional[str] = None) -> bool:
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

    def check_output(self, args: List[str], env: Optional[dict] = None, stderr_on_stdout=False) -> str:
        args = args[:]
        args[0] = str(self.destination / args[0])
        _LOGGER.debug("Executing %s in %s", args, self.destination)
        return subprocess.check_output(
            args,
            cwd=str(self.destination),
            env=env,
            stdin=subprocess.DEVNULL,
            stderr=subprocess.STDOUT if stderr_on_stdout else None,
        ).decode("utf-8")

    def check_call(self, args: List[str], env: Optional[dict] = None) -> None:
        args = args[:]
        args[0] = str(self.destination / args[0])
        _LOGGER.debug("Executing %s in %s", args, self.destination)
        subprocess.check_call(args, cwd=str(self.destination), env=env, stdin=subprocess.DEVNULL)

    def strip_exes(self, staging: StagingDir, paths: Union[bool, List[str]]) -> None:
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

    def run_script(self, staging: StagingDir, from_path: Union[str, Path], lines: List[str]) -> None:
        from_path = Path(from_path)
        if len(lines) > 0:
            _LOGGER.info("Running script")
            script_file = from_path / "ce_script.sh"
            with script_file.open("w", encoding="utf-8") as f:
                f.write("#!/bin/bash\n\nset -euo pipefail\n\n")
                for line in lines:
                    f.write(f"{line}\n")

            script_file.chmod(0o755)
            self.stage_command(staging, [str(script_file)], cwd=from_path)
            script_file.unlink()

    def is_elf(self, maybe_elf_file: Path):
        return b"ELF" in subprocess.check_output(["file", maybe_elf_file])


SimpleJsonType = (int, float, str, bool)


class Installable:
    _check_link: Optional[Callable[[], bool]]
    check_env: Dict
    check_file: Optional[str]
    check_call: List[str]

    def __init__(self, install_context: InstallationContext, config: Dict[str, Any]):
        self.install_context = install_context
        self.config = config
        self.target_name = str(self.config.get("name", "(unnamed)"))
        self.context = self.config_get("context", [])
        self.name = f'{"/".join(self.context)} {self.target_name}'
        self.is_library = False
        self.language = False
        if len(self.context) > 0:
            self.is_library = self.context[0] == "libraries"
            self.language = self.context[1]
        self.depends_by_name = self.config.get("depends", [])
        self.depends: List[Installable] = []
        self.install_always = self.config.get("install_always", False)
        self._check_link = None
        self.build_config = LibraryBuildConfig(config)
        self.check_env = {}
        self.check_file = None
        self.check_call = []
        self.check_stderr_on_stdout = self.config.get("check_stderr_on_stdout", False)
        self.install_path = ""
        self.after_stage_script = self.config_get("after_stage_script", [])
        self._logger = logging.getLogger(self.name)

    def to_json_dict(self) -> Dict[str, Any]:
        return {key: value for key, value in self.__dict__.items() if isinstance(value, SimpleJsonType)}

    def to_json(self) -> str:
        return json.dumps(self.to_json_dict())

    def _setup_check_exe(self, path_name: str) -> None:
        self.check_env = dict([x.replace("%PATH%", path_name).split("=", 1) for x in self.config_get("check_env", [])])

        check_file = self.config_get("check_file", "")
        if check_file:
            self.check_file = os.path.join(path_name, check_file)
        else:
            self.check_call = command_config(self.config_get("check_exe"))
            self.check_call[0] = os.path.join(path_name, self.check_call[0])

    def _setup_check_link(self, source: str, link: str) -> None:
        self._check_link = partial(self.install_context.check_link, source, link)

    def link(self, all_installables: Dict[str, Installable]):
        try:
            self.depends = [all_installables[dep] for dep in self.depends_by_name]
        except KeyError as ke:
            self._logger.error("Unable to find dependency %s in %s", ke, all_installables)
            raise
        dep_re = re.compile("%DEP([0-9]+)%")

        def dep_n(match):
            return str(self.install_context.destination / self.depends[int(match.group(1))].install_path)

        for k in self.check_env.keys():
            self.check_env[k] = dep_re.sub(dep_n, self.check_env[k])

    def find_dependee(self, name: str) -> Installable:
        for i in self.depends:
            if i.name == name:
                return i
        raise RuntimeError(f"Missing dependee {name} - did you forget to add it as a dependency?")

    def verify(self) -> bool:
        return True

    def should_install(self) -> bool:
        return self.install_always or not self.is_installed()

    def should_build(self):
        return (
            self.is_library
            and self.build_config.build_type != "manual"
            and self.build_config.build_type != "none"
            and self.build_config.build_type != ""
        )

    def install(self) -> None:
        self._logger.debug("Ensuring dependees are installed")
        for dependee in self.depends:
            if not dependee.is_installed():
                self._logger.info("Installting required dependee %s", dependee)
                dependee.install()
        self._logger.debug("Dependees installed")

    def is_installed(self) -> bool:
        if self.check_file is None and not self.check_call:
            return True

        if self._check_link and not self._check_link():
            self._logger.debug("Check link returned false")
            return False

        if self.check_file:
            res = (self.install_context.destination / self.check_file).is_file()
            self._logger.debug(
                'Check file for "%s" returned %s', self.install_context.destination / self.check_file, res
            )
            return res

        try:
            res_call = self.install_context.check_output(
                self.check_call, env=self.check_env, stderr_on_stdout=self.check_stderr_on_stdout
            )
            self._logger.debug("Check call returned %s", res_call)
            return True
        except FileNotFoundError:
            self._logger.debug("File not found for %s", self.check_call)
            return False
        except subprocess.CalledProcessError:
            self._logger.debug("Got an error for %s", self.check_call)
            return False

    def config_get(self, config_key: str, default: Optional[Any] = None) -> Any:
        if config_key not in self.config and default is None:
            raise RuntimeError(f"Missing required key '{config_key}' in {self.name}")
        return self.config.get(config_key, default)

    def __repr__(self) -> str:
        return f"Installable({self.name})"

    @property
    def sort_key(self):
        return self.context, [
            (int(num) if num else 0, non) for num, non in re.findall(r"([0-9]+)|([^0-9]+)", self.target_name)
        ]

    @property
    def nightly_like(self) -> bool:
        return False

    def build(self, buildfor):
        if not self.is_library:
            raise RuntimeError("Nothing to build")

        if self.build_config.build_type == "":
            raise RuntimeError("No build_type")

        if self.build_config.build_type in ["cmake", "make"]:
            sourcefolder = os.path.join(self.install_context.destination, self.install_path)
            builder = LibraryBuilder(
                _LOGGER,
                self.language,
                self.context[-1],
                self.target_name,
                sourcefolder,
                self.install_context,
                self.build_config,
            )
            if self.build_config.build_type == "cmake":
                return builder.makebuild(buildfor)
            elif self.build_config.build_type == "make":
                return builder.makebuild(buildfor)
        elif self.build_config.build_type == "cargo":
            builder = RustLibraryBuilder(
                _LOGGER, self.language, self.context[-1], self.target_name, self.install_context, self.build_config
            )
            return builder.makebuild(buildfor)
        else:
            raise RuntimeError("Unsupported build_type")

    def squash_to(self, destination_image: Path):
        destination_image.parent.mkdir(parents=True, exist_ok=True)
        source_folder = self.install_context.destination / self.install_path
        temp_image = destination_image.with_suffix(".tmp")
        temp_image.unlink(missing_ok=True)
        self._logger.info("Squashing %s...", source_folder)
        self.install_context.check_call(
            [
                "/usr/bin/mksquashfs",
                str(source_folder),
                str(temp_image),
                "-all-root",
                "-progress",
                "-comp",
                "zstd",
                "-Xcompression-level",
                "19",
            ]
        )
        temp_image.replace(destination_image)


def command_config(config: Union[List[str], str]) -> List[str]:
    if isinstance(config, str):
        return config.split(" ")
    return config


class GitHubInstallable(Installable):
    def __init__(self, install_context, config):
        super().__init__(install_context, config)
        last_context = self.context[-1]
        self.repo = self.config_get("repo", "")
        self.domainurl = self.config_get("domainurl", "https://github.com")
        self.method = self.config_get("method", "archive")
        self.decompress_flag = self.config_get("decompress_flag", "z")
        self.strip = False
        self.subdir = os.path.join("libs", self.config_get("subdir", last_context))
        self.target_prefix = self.config_get("target_prefix", "")
        self.branch_name = self.target_prefix + self.target_name
        self.install_path = self.config_get("path_name", os.path.join(self.subdir, self.branch_name))
        if self.repo == "":
            raise RuntimeError("Requires repo")
        self.recursive = self.config_get("recursive", True)

        splitrepo = self.repo.split("/")
        self.reponame = splitrepo[1]
        default_untar_dir = f"{self.reponame}-{self.target_name}"
        self.untar_dir = self.config_get("untar_dir", default_untar_dir)

        check_file = self.config_get("check_file", "")
        if check_file == "":
            if self.build_config.build_type == "cmake":
                self.check_file = os.path.join(self.install_path, "CMakeLists.txt")
            elif self.build_config.build_type == "make":
                self.check_file = os.path.join(self.install_path, "Makefile")
            elif self.build_config.build_type == "cake":
                self.check_file = os.path.join(self.install_path, "config.cake")
            elif self.build_config.build_type == "cargo":
                self.check_file = None
            else:
                raise RuntimeError(f"Requires check_file ({last_context})")
        else:
            self.check_file = f"{self.install_path}/{check_file}"

    def _update_args(self):
        if self.recursive:
            return ["--recursive"]
        return []

    def _git(self, staging: StagingDir, *git_args: str) -> str:
        full_args = ["git"] + list(git_args)
        self._logger.debug(shlex.join(full_args))
        result = subprocess.check_output(full_args, cwd=staging.path).decode("utf-8").strip()
        if result:
            self._logger.debug(" -> %s", result)
        return result

    def clone_branch(self, staging: StagingDir):
        dest = os.path.join(self.install_context.destination, self.install_path)
        if not os.path.exists(dest):
            self._git(staging, "clone", "-q", f"{self.domainurl}/{self.repo}.git", dest)
            self._git(staging, "-C", dest, "checkout", "-q", self.branch_name)
        else:
            self._git(staging, "-C", dest, "fetch", "-q")
            self._git(staging, "-C", dest, "reset", "-q", "--hard", "origin")
            self._git(staging, "-C", dest, "checkout", "-q", f"origin/{self.branch_name}")
            self._git(staging, "-C", dest, "branch", "-q", "-D", self.branch_name)
            self._git(staging, "-C", dest, "checkout", "-q", self.branch_name)
        self._git(staging, "-C", dest, "submodule", "sync")
        self._git(staging, "-C", dest, "submodule", "update", "--init", *self._update_args())

    def clone_default(self, staging: StagingDir):
        dest = os.path.join(self.install_context.destination, self.install_path)
        if not os.path.exists(dest):
            self._git(staging, "clone", "-q", f"{self.domainurl}/{self.repo}.git", dest)
        else:
            self._git(staging, "-C", dest, "fetch", "-q")
            remote_name = self._git(staging, "-C", dest, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
            self._git(staging, "-C", dest, "reset", "-q", "--hard", remote_name)
        self._git(staging, "-C", dest, "submodule", "sync")
        self._git(staging, "-C", dest, "submodule", "update", "--init", *self._update_args())

    def get_archive_url(self):
        return f"{self.domainurl}/{self.repo}/archive/{self.target_prefix}{self.target_name}.tar.gz"

    def get_archive_pipecommand(self):
        return ["tar", f"{self.decompress_flag}xf", "-"]

    @property
    def nightly_like(self) -> bool:
        return self.method == "nightlyclone"

    def stage(self, staging: StagingDir):
        if self.method == "archive":
            self.install_context.fetch_url_and_pipe_to(staging, self.get_archive_url(), self.get_archive_pipecommand())
            dest = os.path.join(staging.path, self.untar_dir)
        elif self.method == "clone_branch":
            self.clone_branch(staging)
            dest = os.path.join(self.install_context.destination, self.install_path)
        elif self.method == "nightlyclone":
            self.clone_default(staging)
            dest = os.path.join(self.install_context.destination, self.install_path)
        else:
            raise RuntimeError(f"Unknown Github method {self.method}")

        if self.strip:
            self.install_context.strip_exes(staging, self.strip)

        self.install_context.run_script(staging, dest, self.after_stage_script)

    def verify(self):
        if not super().verify():
            return False
        with self.install_context.new_staging_dir() as staging:
            self.stage(staging)
            return self.install_context.compare_against_staging(staging, self.untar_dir, self.install_path)

    def install(self) -> None:
        super().install()
        with self.install_context.new_staging_dir() as staging:
            self.stage(staging)
            if self.subdir:
                self.install_context.make_subdir(self.subdir)
            if self.method == "archive":
                self.install_context.move_from_staging(staging, self.untar_dir, self.install_path)

    def __repr__(self) -> str:
        return f"GitHubInstallable({self.name}, {self.install_path})"


class GitLabInstallable(GitHubInstallable):
    def __init__(self, install_context, config):
        super().__init__(install_context, config)
        self.domainurl = self.config_get("domainurl", "https://gitlab.com")

    def get_archive_url(self):
        return f"{self.domainurl}/{self.repo}/-/archive/{self.target_name}/{self.reponame}-{self.target_name}.tar.gz"

    def __repr__(self) -> str:
        return f"GitLabInstallable({self.name}, {self.install_path})"


class BitbucketInstallable(GitHubInstallable):
    def __init__(self, install_context, config):
        super().__init__(install_context, config)
        self.domainurl = self.config_get("domainurl", "https://bitbucket.org")

    def get_archive_url(self):
        return f"{self.domainurl}/{self.repo}/downloads/{self.reponame}-{self.target_name}.tar.gz"

    def __repr__(self) -> str:
        return f"BitbucketInstallable({self.name}, {self.install_path})"


class S3TarballInstallable(Installable):
    def __init__(self, install_context: InstallationContext, config: Dict[str, Any]):
        super().__init__(install_context, config)
        self.subdir = self.config_get("subdir", "")
        last_context = self.context[-1]
        if self.subdir:
            default_s3_path_prefix = f"{self.subdir}-{last_context}-{self.target_name}"
            default_path_name = f"{self.subdir}/{last_context}-{self.target_name}"
            default_untar_dir = f"{last_context}-{self.target_name}"
        else:
            default_s3_path_prefix = f"{last_context}-{self.target_name}"
            default_path_name = f"{last_context}-{self.target_name}"
            default_untar_dir = default_path_name
        s3_path_prefix = self.config_get("s3_path_prefix", default_s3_path_prefix)
        self.install_path = self.config_get("path_name", default_path_name)
        self.untar_dir = self.config_get("untar_dir", default_untar_dir)
        compression = self.config_get("compression", "xz")
        if compression == "xz":
            self.s3_path = f"{s3_path_prefix}.tar.xz"
            self.decompress_flag = "J"
        elif compression == "gz":
            self.s3_path = f"{s3_path_prefix}.tar.gz"
            self.decompress_flag = "z"
        elif compression == "bz2":
            self.s3_path = f"{s3_path_prefix}.tar.bz2"
            self.decompress_flag = "j"
        else:
            raise RuntimeError(f"Unknown compression {compression}")
        self.strip = self.config_get("strip", False)
        self._setup_check_exe(self.install_path)

    def stage(self, staging: StagingDir) -> None:
        self.install_context.fetch_s3_and_pipe_to(staging, self.s3_path, ["tar", f"{self.decompress_flag}xf", "-"])
        if self.strip:
            self.install_context.strip_exes(staging, self.strip)

        self.install_context.run_script(staging, self.s3_path, self.after_stage_script)

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
            if self.subdir:
                self.install_context.make_subdir(self.subdir)

            self.install_context.move_from_staging(staging, self.untar_dir, self.install_path)

    def __repr__(self) -> str:
        return f"S3TarballInstallable({self.name}, {self.install_path})"


class NightlyInstallable(Installable):
    def __init__(self, install_context: InstallationContext, config: Dict[str, Any]):
        super().__init__(install_context, config)
        self.subdir = self.config_get("subdir", "")
        self.strip = self.config_get("strip", False)
        compiler_name = self.config_get("compiler_name", f"{self.context[-1]}-{self.target_name}")
        current = s3_available_compilers()
        if compiler_name not in current:
            raise RuntimeError(f"Unable to find nightlies for {compiler_name}")
        most_recent = max(current[compiler_name])
        self._logger.info("Most recent %s is %s", compiler_name, most_recent)
        path_name_prefix = self.config_get("path_name_prefix", compiler_name)
        s3_name = self.config_get("s3_name", compiler_name)
        self.s3_path = f"{s3_name}-{most_recent}"
        self.local_path = f"{path_name_prefix}-{most_recent}"
        self.install_path = os.path.join(self.subdir, f"{path_name_prefix}-{most_recent}")
        self.compiler_pattern = os.path.join(self.subdir, f"{path_name_prefix}-*")
        self.path_name_symlink = self.config_get("symlink", os.path.join(self.subdir, f"{path_name_prefix}"))
        self.num_to_keep = self.config_get("num_to_keep", 5)
        self._setup_check_exe(self.install_path)
        self._setup_check_link(self.local_path, self.path_name_symlink)

    @property
    def nightly_like(self) -> bool:
        return True

    def stage(self, staging: StagingDir) -> None:
        self.install_context.fetch_s3_and_pipe_to(staging, f"{self.s3_path}.tar.xz", ["tar", "Jxf", "-"])
        if self.strip:
            self.install_context.strip_exes(staging, self.strip)
        self.install_context.run_script(staging, staging.path / self.local_path, self.after_stage_script)

    def verify(self) -> bool:
        if not super().verify():
            return False
        with self.install_context.new_staging_dir() as staging:
            self.stage(staging)
            return self.install_context.compare_against_staging(staging, self.local_path, self.install_path)

    def should_install(self) -> bool:
        return True

    def install(self) -> None:
        super().install()
        with self.install_context.new_staging_dir() as staging:
            self.stage(staging)

            # Do this first, and add one for the file we haven't yet installed... (then dry run works)
            num_to_keep = self.num_to_keep + 1
            all_versions = list(sorted(self.install_context.glob(self.compiler_pattern)))
            for to_remove in all_versions[:-num_to_keep]:
                self.install_context.remove_dir(to_remove)

            self.install_context.move_from_staging(staging, self.local_path, self.install_path)
            self.install_context.set_link(Path(self.local_path), self.path_name_symlink)

    def __repr__(self) -> str:
        return f"NightlyInstallable({self.name}, {self.install_path})"


class TarballInstallable(Installable):
    def __init__(self, install_context: InstallationContext, config: Dict[str, Any]):
        super().__init__(install_context, config)
        self.install_path = self.config_get("dir")
        self.install_path_symlink = self.config_get("symlink", False)
        self.untar_path = self.config_get("untar_dir", self.install_path)
        if self.config_get("create_untar_dir", False):
            self.untar_to = self.untar_path
        else:
            self.untar_to = "."
        self.url = self.config_get("url")
        if self.config_get("compression") == "xz":
            decompress_flag = "J"
        elif self.config_get("compression") == "gz":
            decompress_flag = "z"
        elif self.config_get("compression") == "bz2":
            decompress_flag = "j"
        elif self.config_get("compression") == "tar":
            decompress_flag = ""
        else:
            raise RuntimeError(f'Unknown compression {self.config_get("compression")}')
        self.configure_command = command_config(self.config_get("configure_command", []))
        self.tar_cmd = ["tar", f"{decompress_flag}xf", "-"]
        strip_components = self.config_get("strip_components", 0)
        if strip_components:
            self.tar_cmd += ["--strip-components", str(strip_components)]
        extract_only = self.config_get("extract_only", "")
        if extract_only:
            self.tar_cmd += [extract_only]
        self.strip = self.config_get("strip", False)
        self._setup_check_exe(self.install_path)
        if self.install_path_symlink:
            self._setup_check_link(self.install_path, self.install_path_symlink)
        self.remove_older_pattern = self.config_get("remove_older_pattern", "")
        self.num_to_keep = self.config_get("num_to_keep", 5)

    def stage(self, staging: StagingDir) -> None:
        self.install_context.fetch_url_and_pipe_to(staging, f"{self.url}", self.tar_cmd, self.untar_to)
        if self.configure_command:
            self.install_context.stage_command(staging, self.configure_command)
        if self.strip:
            self.install_context.strip_exes(staging, self.strip)
        if not (staging.path / self.untar_path).is_dir():
            raise RuntimeError(f"After unpacking, {self.untar_path} was not a directory")
        self.install_context.run_script(staging, staging.path / self.untar_to, self.after_stage_script)

    def verify(self) -> bool:
        if not super().verify():
            return False
        with self.install_context.new_staging_dir() as staging:
            self.stage(staging)
            return self.install_context.compare_against_staging(staging, self.untar_path, self.install_path)

    def install(self) -> None:
        super().install()
        with self.install_context.new_staging_dir() as staging:
            self.stage(staging)

            if self.remove_older_pattern:
                # Do this first, and add one for the file we haven't yet installed... (then dry run works)
                num_to_keep = self.num_to_keep + 1
                all_versions = list(sorted(self.install_context.glob(self.remove_older_pattern)))
                for to_remove in all_versions[:-num_to_keep]:
                    self.install_context.remove_dir(to_remove)

            self.install_context.move_from_staging(staging, self.untar_path, self.install_path)
            if self.install_path_symlink:
                self.install_context.set_link(Path(self.install_path), self.install_path_symlink)

    def __repr__(self) -> str:
        return f"TarballInstallable({self.name}, {self.install_path})"


class NightlyTarballInstallable(TarballInstallable):
    def __init__(self, install_context: InstallationContext, config: Dict[str, Any]):
        super().__init__(install_context, config)

        if not self.install_path_symlink:
            self.install_path_symlink = f"{self.install_path}"

        if not self.remove_older_pattern:
            self.remove_older_pattern = f"{self.install_path}-*"

        today = datetime.today().strftime("%Y%m%d")
        self.install_path = f"{self.install_path}-{today}"

        # redo exe checks
        self._setup_check_exe(self.install_path)
        self._setup_check_link(self.install_path, self.install_path_symlink)

    @property
    def nightly_like(self) -> bool:
        return True

    def __repr__(self) -> str:
        return f"NightlyTarballInstallable({self.name}, {self.install_path})"


class ZipArchiveInstallable(Installable):
    def __init__(self, install_context: InstallationContext, config: Dict[str, Any]):
        super().__init__(install_context, config)
        self.url = self.config_get("url")
        self.install_path = self.config_get("dir")
        self.extract_into_folder = self.config_get("extract_into_folder", False)
        self.folder_to_rename = self.config_get("folder", None if not self.extract_into_folder else "tmp")
        self.configure_command = command_config(self.config_get("configure_command", []))
        self.strip = self.config_get("strip", False)
        self._setup_check_exe(self.install_path)

    def stage(self, staging: StagingDir) -> None:
        # Unzip does not support stdin piping so we need to create a file
        with (staging.path / "distribution.zip").open("wb") as fd:
            self.install_context.fetch_to(self.url, fd)
            unzip_cmd = ["unzip", fd.name]
            if self.extract_into_folder:
                unzip_cmd.extend(["-d", self.folder_to_rename])
            self.install_context.stage_command(staging, unzip_cmd)
            self.install_context.stage_command(staging, ["mv", self.folder_to_rename, self.install_path])
        if self.configure_command:
            self.install_context.stage_command(staging, self.configure_command)
        if self.strip:
            self.install_context.strip_exes(staging, self.strip)
        full_install_path = staging.path / self.install_path
        if not full_install_path.is_dir():
            raise RuntimeError(f"After unpacking, {self.install_path} was not a directory")
        self.install_context.run_script(staging, full_install_path, self.after_stage_script)

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
        return f"ZipArchiveInstallable({self.name}, {self.install_path})"


class RestQueryTarballInstallable(TarballInstallable):
    def __init__(self, install_context: InstallationContext, config: Dict[str, Any]):
        super().__init__(install_context, config)
        document = self.install_context.fetch_rest_query(self.config_get("url"))
        # pylint: disable-next=eval-used
        self.url = eval(self.config_get("query"), {}, dict(document=document))
        if not self.url:
            self._logger.warning("No installation candidate found")
        else:
            self._logger.info("resolved to %s", self.url)

    def should_install(self) -> bool:
        if not self.url:
            return False
        return super().should_install()

    def __repr__(self) -> str:
        return f"RestQueryTarballInstallable({self.name}, {self.install_path})"


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


class PipInstallable(Installable):
    MV_URL = "https://raw.githubusercontent.com/brbsix/virtualenv-mv/master/virtualenv-mv"

    def __init__(self, install_context: InstallationContext, config: Dict[str, Any]):
        super().__init__(install_context, config)
        self.install_path = self.config_get("dir")
        self._setup_check_exe(self.install_path)
        self.package = self.config_get("package")
        self.python = self.config_get("python")

    def stage(self, staging: StagingDir) -> None:
        venv = staging.path / self.install_path
        self.install_context.check_output([self.python, "-mvenv", str(venv)])
        self.install_context.check_output([str(venv / "bin" / "pip"), "install", self.package])

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
            mv_script = staging.path / "virtualenv-mv"
            with mv_script.open("wb") as f:
                self.install_context.fetch_to(PipInstallable.MV_URL, f)
            mv_script.chmod(0o755)

            def mv_venv(source, dest):
                self.install_context.check_output([str(mv_script), str(source), str(dest)])

            self.install_context.move_from_staging(staging, self.install_path, do_staging_move=mv_venv)

    def __repr__(self) -> str:
        return f"PipInstallable({self.name}, {self.install_path})"


@functools.lru_cache(maxsize=1)
def solidity_available_releases(context: InstallationContext, list_url: str):
    response = context.fetcher.get(list_url)
    return response.json()["releases"]


class SingleFileInstallable(Installable):
    def __init__(self, install_context: InstallationContext, config: Dict[str, Any]):
        super().__init__(install_context, config)
        self.install_path = self.config_get("dir")
        self.url = self.config_get("url")
        self.filename = self.config_get("filename")
        self._setup_check_exe(self.install_path)

    def stage(self, staging: StagingDir) -> None:
        out_path = staging.path / self.install_path
        out_path.mkdir()
        out_file_path = out_path / self.filename
        with out_file_path.open("wb") as f:
            self.install_context.fetch_to(self.url, f)
        out_file_path.chmod(0o755)

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
        return f"SingleFileInstallable({self.name}, {self.install_path})"


class SolidityInstallable(SingleFileInstallable):
    def __init__(self, install_context: InstallationContext, config: Dict[str, Any]):
        super().__init__(install_context, config)
        self.install_path = self.config_get("dir")
        artifacts = solidity_available_releases(self.install_context, self.url + "/list.json")
        release_path = artifacts[self.target_name]
        if self.target_name not in artifacts:
            raise RuntimeError(f"Unable to find solidity {self.target_name}")
        self.url = f"{self.url}/{release_path}"
        self.filename = self.config_get("filename")
        self._setup_check_exe(self.install_path)

    def __repr__(self) -> str:
        return f"SolidityInstallable({self.name}, {self.install_path})"


class CratesIOInstallable(Installable):
    def is_installed(self) -> bool:
        return True


def targets_from(node, enabled, base_config=None):
    if base_config is None:
        base_config = {}
    return _targets_from(node, enabled, [], "", base_config)


def _targets_from(node, enabled, context, name, base_config):
    if not node:
        return

    if isinstance(node, list):
        for child in node:
            for target in _targets_from(child, enabled, context, name, base_config):
                yield target
        return

    if not isinstance(node, dict):
        return

    if "if" in node:
        if isinstance(node["if"], list):
            condition = set(node["if"])
        else:
            condition = {node["if"]}
        if set(enabled).intersection(condition) != condition:
            return

    context = context[:]
    if name:
        context.append(name)
    base_config = dict(base_config)
    for key, value in node.items():
        if key != "targets" and is_value_type(value):
            base_config[key] = value

    for child_name, child in node.items():
        for target in _targets_from(child, enabled, context, child_name, base_config):
            yield target

    if "targets" in node:
        base_config["context"] = context
        for target in node["targets"]:
            if isinstance(target, float):
                raise RuntimeError(f"Target {target} was parsed as a float. Enclose in quotes")
            if isinstance(target, str):
                target = {"name": target, "underscore_name": target.replace(".", "_")}
            yield expand_target(ChainMap(target, base_config), context)


INSTALLER_TYPES = {
    "tarballs": TarballInstallable,
    "restQueryTarballs": RestQueryTarballInstallable,
    "s3tarballs": S3TarballInstallable,
    "nightlytarballs": NightlyTarballInstallable,
    "nightly": NightlyInstallable,
    "script": ScriptInstallable,
    "solidity": SolidityInstallable,
    "singleFile": SingleFileInstallable,
    "github": GitHubInstallable,
    "gitlab": GitLabInstallable,
    "bitbucket": BitbucketInstallable,
    "rust": RustInstallable,
    "pip": PipInstallable,
    "ziparchive": ZipArchiveInstallable,
    "cratesio": CratesIOInstallable,
}


def installers_for(install_context, nodes, enabled):
    for target in targets_from(
        nodes,
        enabled,
        dict(
            destination=install_context.destination,
            yaml_dir=install_context.yaml_dir,
            resource_dir=install_context.resource_dir,
            now=datetime.now(),
        ),
    ):
        assert "type" in target
        target_type = target["type"]
        if target_type not in INSTALLER_TYPES:
            raise RuntimeError(f"Unknown installer type {target_type}")
        installer_type = INSTALLER_TYPES[target_type]
        yield installer_type(install_context, target)
