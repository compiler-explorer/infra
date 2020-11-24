from __future__ import annotations

import functools
import glob
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
from collections import defaultdict, ChainMap
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Sequence, Collection, List, Union, Dict, Any, IO, Callable

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

VERSIONED_RE = re.compile(r'^(.*)-([0-9.]+)$')

NO_DEFAULT = "__no_default__"

logger = logging.getLogger(__name__)


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
    def __init__(self, destination: Path, staging: Path, s3_url: str, dry_run: bool, is_nightly_enabled: bool,
                 cache: Optional[Path], yaml_dir: Path):
        self.destination = destination
        self.staging = staging
        self.s3_url = s3_url
        self.dry_run = dry_run
        self.is_nightly_enabled = is_nightly_enabled
        retry_strategy = requests.adapters.Retry(
            total=10,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            method_whitelist=["HEAD", "GET", "OPTIONS"]
        )
        adapter = requests.adapters.HTTPAdapter(max_retries=retry_strategy)
        http = requests.Session()
        http.mount("https://", adapter)
        http.mount("http://", adapter)
        if cache:
            self.info(f"Using cache {cache}")
            self.fetcher = CacheControl(http, cache=FileCache(cache))
        else:
            self.info("Making uncached requests")
            self.fetcher = http
        self.yaml_dir = yaml_dir

    def debug(self, message: str) -> None:
        logger.debug(message)

    def info(self, message: str) -> None:
        logger.info(message)

    def warn(self, message: str) -> None:
        logger.warning(message)

    def error(self, message: str) -> None:
        logger.error(message)

    def clean_staging(self) -> None:
        self.debug(f"Cleaning staging dir {self.staging}")
        if self.staging.is_dir():
            subprocess.check_call(["chmod", "-R", "u+w", self.staging])
            shutil.rmtree(self.staging, ignore_errors=True)
        self.debug(f"Recreating staging dir {self.staging}")
        self.staging.mkdir(parents=True)

    def fetch_rest_query(self, url: str) -> Dict:
        self.debug(f'Fetching {url}')
        return yaml.load(self.fetcher.get(url).text, Loader=ConfigSafeLoader)

    def fetch_to(self, url: str, fd: IO[bytes]) -> None:
        self.debug(f'Fetching {url}')
        request = self.fetcher.get(url, stream=True)
        if not request.ok:
            self.error(f'Failed to fetch {url}: {request}')
            raise FetchFailure(f'Fetch failure for {url}: {request}')
        fetched = 0
        length = int(request.headers.get('content-length', 0))
        self.info(f'Fetching {url} ({length} bytes)')
        report_every_secs = 5
        report_time = time.time() + report_every_secs
        for chunk in request.iter_content(chunk_size=4 * 1024 * 1024):
            fd.write(chunk)
            fetched += len(chunk)
            now = time.time()
            if now >= report_time:
                if length != 0:
                    self.info(f'{100.0 * fetched / length:.1f}% of {url}...')
                report_time = now + report_every_secs
        self.info(f'100% of {url}')
        fd.flush()

    def fetch_url_and_pipe_to(self, url: str, command: Sequence[str], subdir: Union[Path, str] = '.') -> None:
        untar_dir = self.staging / subdir
        untar_dir.mkdir(parents=True, exist_ok=True)
        # We stream to a temporary file first before then piping this to the command
        # as sometimes the command can take so long the URL endpoint closes the door on us
        with tempfile.TemporaryFile() as fd:
            self.fetch_to(url, fd)
            fd.seek(0)
            self.info(f'Piping to {" ".join(command)}')
            subprocess.check_call(command, stdin=fd, cwd=str(untar_dir))

    def stage_command(self, command: Sequence[str], cwd: Optional[Path] = None) -> None:
        self.info(f'Staging with {" ".join(command)}')
        subprocess.check_call(command, cwd=str(cwd or self.staging))

    def fetch_s3_and_pipe_to(self, s3: str, command: Sequence[str]) -> None:
        return self.fetch_url_and_pipe_to(f'{self.s3_url}/{s3}', command)

    def make_subdir(self, subdir: str) -> None:
        (self.destination / subdir).mkdir(parents=True, exist_ok=True)

    def read_link(self, link: str) -> str:
        return os.readlink(str(self.destination / link))

    def set_link(self, source: Path, dest: str) -> None:
        if self.dry_run:
            self.info(f'Would symlink {source} to {dest}')
            return

        full_dest = self.destination / dest
        if full_dest.exists():
            full_dest.unlink()
        self.info(f'Symlinking {dest} to {source}')
        os.symlink(str(source), str(full_dest))

    def glob(self, pattern: str) -> Collection[str]:
        return [os.path.relpath(x, str(self.destination)) for x in glob.glob(str(self.destination / pattern))]

    def remove_dir(self, directory: Union[str, Path]) -> None:
        if self.dry_run:
            self.info(f'Would remove directory {directory} but in dry-run mode')
        else:
            shutil.rmtree(str(self.destination / directory), ignore_errors=True)
            self.info(f'Removing {directory}')

    def check_link(self, source: str, link: str) -> bool:
        try:
            link = self.read_link(link)
            self.debug(f'readlink returned {link}')
            return link == source
        except FileNotFoundError:
            self.debug(f'File not found for {link}')
            return False

    def move_from_staging(self, source_str: str, dest_str: Optional[str] = None,
                          do_staging_move=lambda source, dest: source.replace(dest)) -> None:
        dest_str = dest_str or source_str
        existing_dir_rename = self.staging / "temp_orig"
        source = self.staging / source_str
        dest = self.destination / dest_str
        if self.dry_run:
            self.info(f'Would install {source} to {dest} but in dry-run mode')
            return
        dest.parent.mkdir(parents=True, exist_ok=True)
        self.info(f'Moving from staging ({source}) to final destination ({dest})')
        if not source.is_dir():
            staging_contents = subprocess.check_output(['ls', '-l', self.staging]).decode('utf-8')
            self.info(f"Directory listing of staging:\n{staging_contents}")
            raise RuntimeError(f"Missing source '{source}'")
        # Some tar'd up GCCs are actually marked read-only...
        subprocess.check_call(["chmod", "u+w", source])
        state = ''
        if dest.is_dir():
            self.info(f'Destination {dest} exists, temporarily moving out of the way (to {existing_dir_rename})')
            dest.replace(existing_dir_rename)
            state = 'old_renamed'
        try:
            do_staging_move(source, dest)
            if state == 'old_renamed':
                state = 'old_needs_remove'
        finally:
            if state == 'old_needs_remove':
                self.debug(f'Removing temporarily moved {existing_dir_rename}')
                shutil.rmtree(existing_dir_rename, ignore_errors=True)
            elif state == 'old_renamed':
                self.warn('Moving old destination back')
                existing_dir_rename.replace(dest)

    def compare_against_staging(self, source_str: str, dest_str: Optional[str] = None) -> bool:
        dest_str = dest_str or source_str
        source = self.staging / source_str
        dest = self.destination / dest_str
        self.info(f'Comparing {source} vs {dest}...')
        result = subprocess.call(['diff', '-r', source, dest])
        if result == 0:
            self.info('Contents match')
        else:
            self.warn('Contents differ')
        return result == 0

    def check_output(self, args: List[str], env: Optional[dict] = None) -> str:
        args = args[:]
        args[0] = str(self.destination / args[0])
        logger.debug('Executing %s in %s', args, self.destination)
        return subprocess.check_output(args, cwd=str(self.destination), env=env, stdin=subprocess.DEVNULL).decode(
            'utf-8')

    def check_call(self, args: List[str], env: Optional[dict] = None) -> None:
        args = args[:]
        args[0] = str(self.destination / args[0])
        logger.debug('Executing %s in %s', args, self.destination)
        subprocess.check_call(args, cwd=str(self.destination), env=env, stdin=subprocess.DEVNULL)

    def strip_exes(self, paths: Union[bool, List[str]]) -> None:
        if isinstance(paths, bool):
            if not paths:
                return
            paths = ['.']
        to_strip = []
        for path_part in paths:
            path = self.staging / path_part
            logger.debug("Looking for executables to strip in %s", path)
            if not path.is_dir():
                raise RuntimeError(f"While looking for files to strip, {path} was not a directory")
            for dirpath, _, filenames in os.walk(str(path)):
                for filename in filenames:
                    full_path = os.path.join(dirpath, filename)
                    if os.access(full_path, os.X_OK):
                        to_strip.append(full_path)

        # Deliberately ignore errors
        subprocess.call(['strip'] + to_strip)

    def run_script(self, frompath: Union[str, Path], lines: List[str]) -> None:
        if len(lines) > 0:
            self.info('Running script')
            scriptfile = os.path.join(frompath, 'ce_script.sh')
            f = open(scriptfile, 'w')
            f.write('#!/bin/bash\n\nset -euo pipefail\n\n')
            for line in lines:
                f.write(f'{line}\n')
            f.close()

            subprocess.check_call(['/bin/chmod', '+x', scriptfile])
            subprocess.check_call([scriptfile], cwd=frompath)

            os.remove(scriptfile)

    def is_elf(self, maybe_elf_file: Path):
        return b'ELF' in subprocess.check_output(['file', maybe_elf_file])

    def set_rpath(self, elf_file: Path, rpath: str):
        # TODO: sometime we'll need a way of finding patchelf
        self.info(f'Setting rpath of {elf_file} to {rpath}')
        subprocess.check_call([self.destination / 'patchelf-0.8' / 'src' / 'patchelf', '--set-rpath', rpath, elf_file])


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
        self.depends = self.config.get('depends', [])
        self.install_always = self.config.get('install_always', False)
        self._check_link = None
        self.build_config = LibraryBuildConfig(config)
        self.check_env = {}
        self.check_file = None
        self.check_call = []
        self.install_path = ''
        self.after_stage_script = self.config_get('after_stage_script', [])

    def _setup_check_exe(self, path_name: str) -> None:
        self.check_env = dict([x.replace('%PATH%', path_name).split('=', 1) for x in self.config_get('check_env', [])])

        check_file = self.config_get('check_file', '')
        if check_file:
            self.check_file = os.path.join(path_name, check_file)
        else:
            self.check_call = command_config(self.config_get('check_exe'))
            self.check_call[0] = os.path.join(path_name, self.check_call[0])

    def _setup_check_link(self, source: str, link: str) -> None:
        self._check_link = lambda: self.install_context.check_link(source, link)

    def link(self, all_installables: Dict[str, Installable]):
        try:
            self.depends = [all_installables[dep] for dep in self.depends]
        except KeyError as ke:
            self.error(f"Unable to find dependency {ke}")
            raise

    def debug(self, message: str) -> None:
        self.install_context.debug(f'{self.name}: {message}')

    def info(self, message: str) -> None:
        self.install_context.info(f'{self.name}: {message}')

    def warn(self, message: str) -> None:
        self.install_context.warn(f'{self.name}: {message}')

    def error(self, message: str) -> None:
        self.install_context.error(f'{self.name}: {message}')

    def verify(self) -> bool:
        return True

    def should_install(self) -> bool:
        return self.install_always or not self.is_installed()

    def should_build(self):
        return self.is_library and self.build_config.build_type != "manual" and self.build_config.build_type != "none"

    def install(self) -> bool:
        self.debug("Ensuring dependees are installed")
        any_missing = False
        for dependee in self.depends:
            if not dependee.is_installed():
                self.warn("Required dependee {} not installed".format(dependee))
                any_missing = True
        if any_missing:
            return False
        self.debug("Dependees ok")
        return True

    def is_installed(self) -> bool:
        if self._check_link and not self._check_link():
            self.debug('Check link returned false')
            return False

        if self.check_file:
            res = (self.install_context.destination / self.check_file).is_file()
            self.debug(f'Check file for "{self.check_file}" returned {res}')
            return res

        try:
            res_call = self.install_context.check_output(self.check_call, env=self.check_env)
            self.debug(f'Check call returned {res_call}')
            return True
        except FileNotFoundError:
            self.debug(f'File not found for {self.check_call}')
            return False
        except subprocess.CalledProcessError:
            self.debug(f'Got an error for {self.check_call}')
            return False

    def config_get(self, config_key: str, default: Optional[Any] = None) -> Any:
        if config_key not in self.config and default is None:
            raise RuntimeError(f"Missing required key '{config_key}' in {self.name}")
        return self.config.get(config_key, default)

    def __repr__(self) -> str:
        return f'Installable({self.name})'

    @property
    def sort_key(self):
        return self.context, [
            (int(num) if num else 0, non) for num, non in re.findall(r'([0-9]+)|([^0-9]+)', self.target_name)
        ]

    def build(self, buildfor):
        if not self.is_library:
            raise RuntimeError('Nothing to build')

        if self.build_config.build_type == "":
            raise RuntimeError('No build_type')

        sourcefolder = os.path.join(self.install_context.destination, self.install_path)
        builder = LibraryBuilder(logger, self.language, self.context[-1], self.target_name, sourcefolder,
                                 self.install_context, self.build_config)

        if self.build_config.build_type == "cmake":
            return builder.makebuild(buildfor)
        elif self.build_config.build_type == "make":
            return builder.makebuild(buildfor)
        else:
            raise RuntimeError('Unsupported build_type')

    def squash_to(self, destination_image: Path):
        destination_image.parent.mkdir(parents=True, exist_ok=True)
        source_folder = self.install_context.destination / self.install_path
        temp_image = destination_image.with_suffix(".tmp")
        self.info(f"Squashing {source_folder}...")
        self.install_context.check_call([
            "/usr/bin/mksquashfs",
            str(source_folder),
            str(temp_image),
            "-all-root",
            "-progress",
            "-comp", "zstd",
            "-Xcompression-level", "19"
        ])
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
        self.subdir = os.path.join('libs', self.config_get("subdir", last_context))
        self.target_prefix = self.config_get("target_prefix", "")
        self.branch_name = self.target_prefix + self.target_name
        self.install_path = self.config_get('path_name', os.path.join(self.subdir, self.branch_name))
        if self.repo == "":
            raise RuntimeError('Requires repo')
        self.recursive = self.config_get("recursive", True)

        splitrepo = self.repo.split('/')
        self.reponame = splitrepo[1]
        default_untar_dir = f'{self.reponame}-{self.target_name}'
        self.untar_dir = self.config_get("untar_dir", default_untar_dir)

        check_file = self.config_get("check_file", "")
        if check_file == "":
            if self.build_config.build_type == "cmake":
                self.check_file = os.path.join(self.install_path, 'CMakeLists.txt')
            elif self.build_config.build_type == "make":
                self.check_file = os.path.join(self.install_path, 'Makefile')
            elif self.build_config.build_type == "cake":
                self.check_file = os.path.join(self.install_path, 'config.cake')
            else:
                raise RuntimeError(f'Requires check_file ({last_context})')
        else:
            self.check_file = f'{self.install_path}/{check_file}'

    def _update_args(self):
        if self.recursive:
            return ['--recursive']
        return []

    def clone_branch(self):
        dest = os.path.join(self.install_context.destination, self.install_path)
        if not os.path.exists(dest):
            subprocess.check_call(['git', 'clone', '-q', f'{self.domainurl}/{self.repo}.git', dest],
                                  cwd=self.install_context.staging)
            subprocess.check_call(['git', '-C', dest, 'checkout', '-q', self.branch_name],
                                  cwd=self.install_context.staging)
        else:
            subprocess.check_call(['git', '-C', dest, 'fetch', '-q'], cwd=self.install_context.staging)
            subprocess.check_call(['git', '-C', dest, 'reset', '-q', '--hard', 'origin'],
                                  cwd=self.install_context.staging)
            subprocess.check_call(['git', '-C', dest, 'checkout', '-q', f'origin/{self.branch_name}'],
                                  cwd=self.install_context.staging)
            subprocess.check_call(['git', '-C', dest, 'branch', '-q', '-D', self.branch_name],
                                  cwd=self.install_context.staging)
            subprocess.check_call(['git', '-C', dest, 'checkout', '-q', self.branch_name],
                                  cwd=self.install_context.staging)
        subprocess.check_call(['git', '-C', dest, 'submodule', 'sync'], cwd=self.install_context.staging)
        subprocess.check_call(['git', '-C', dest, 'submodule', 'update', '--init'] + self._update_args(),
                              cwd=self.install_context.staging)

    def clone_default(self):
        dest = os.path.join(self.install_context.destination, self.install_path)
        if not os.path.exists(dest):
            subprocess.check_call(['git', 'clone', '-q', f'{self.domainurl}/{self.repo}.git', dest],
                                  cwd=self.install_context.staging)
        else:
            subprocess.check_call(['git', '-C', dest, 'fetch', '-q'], cwd=self.install_context.staging)
            subprocess.check_call(['git', '-C', dest, 'reset', '-q', '--hard', 'origin'],
                                  cwd=self.install_context.staging)
        subprocess.check_call(['git', '-C', dest, 'submodule', 'sync'], cwd=self.install_context.staging)
        subprocess.check_call(['git', '-C', dest, 'submodule', 'update', '--init'] + self._update_args(),
                              cwd=self.install_context.staging)

    def get_archive_url(self):
        return f'{self.domainurl}/{self.repo}/archive/{self.target_prefix}{self.target_name}.tar.gz'

    def get_archive_pipecommand(self):
        return ['tar', f'{self.decompress_flag}xf', '-']

    def stage(self):
        self.install_context.clean_staging()
        if self.method == "archive":
            self.install_context.fetch_url_and_pipe_to(self.get_archive_url(), self.get_archive_pipecommand())
        elif self.method == "clone_branch":
            self.clone_branch()
        elif self.method == "nightlyclone":
            self.clone_default()
        else:
            raise RuntimeError(f'Unknown Github method {self.method}')

        if self.strip:
            self.install_context.strip_exes(self.strip)

        dest = os.path.join(self.install_context.destination, self.install_path)
        self.install_context.run_script(dest, self.after_stage_script)

    def verify(self):
        if not super().verify():
            return False
        self.stage()
        return self.install_context.compare_against_staging(self.untar_dir, self.install_path)

    def install(self):
        if not super().install():
            return False
        self.stage()
        if self.subdir:
            self.install_context.make_subdir(self.subdir)
        if self.method == "archive":
            self.install_context.move_from_staging(self.untar_dir, self.install_path)
        return True

    def __repr__(self) -> str:
        return f'GitHubInstallable({self.name}, {self.install_path})'


class GitLabInstallable(GitHubInstallable):
    def __init__(self, install_context, config):
        super().__init__(install_context, config)
        self.domainurl = self.config_get("domainurl", "https://gitlab.com")

    def get_archive_url(self):
        return f'{self.domainurl}/{self.repo}/-/archive/{self.target_name}/{self.reponame}-{self.target_name}.tar.gz'

    def __repr__(self) -> str:
        return f'GitLabInstallable({self.name}, {self.install_path})'


class BitbucketInstallable(GitHubInstallable):
    def __init__(self, install_context, config):
        super().__init__(install_context, config)
        self.domainurl = self.config_get("domainurl", "https://bitbucket.org")

    def get_archive_url(self):
        return f'{self.domainurl}/{self.repo}/downloads/{self.reponame}-{self.target_name}.tar.gz'

    def __repr__(self) -> str:
        return f'BitbucketInstallable({self.name}, {self.install_path})'


class S3TarballInstallable(Installable):
    def __init__(self, install_context: InstallationContext, config: Dict[str, Any]):
        super().__init__(install_context, config)
        self.subdir = self.config_get("subdir", "")
        last_context = self.context[-1]
        if self.subdir:
            default_s3_path_prefix = f'{self.subdir}-{last_context}-{self.target_name}'
            default_path_name = f'{self.subdir}/{last_context}-{self.target_name}'
            default_untar_dir = f'{last_context}-{self.target_name}'
        else:
            default_s3_path_prefix = f'{last_context}-{self.target_name}'
            default_path_name = f'{last_context}-{self.target_name}'
            default_untar_dir = default_path_name
        s3_path_prefix = self.config_get('s3_path_prefix', default_s3_path_prefix)
        self.install_path = self.config_get('path_name', default_path_name)
        self.untar_dir = self.config_get("untar_dir", default_untar_dir)
        compression = self.config_get('compression', 'xz')
        if compression == 'xz':
            self.s3_path = f'{s3_path_prefix}.tar.xz'
            self.decompress_flag = 'J'
        elif compression == 'gz':
            self.s3_path = f'{s3_path_prefix}.tar.gz'
            self.decompress_flag = 'z'
        elif compression == 'bz2':
            self.s3_path = f'{s3_path_prefix}.tar.bz2'
            self.decompress_flag = 'j'
        else:
            raise RuntimeError(f'Unknown compression {compression}')
        self.strip = self.config_get('strip', False)
        self._setup_check_exe(self.install_path)

    def stage(self) -> None:
        self.install_context.clean_staging()
        self.install_context.fetch_s3_and_pipe_to(self.s3_path, ['tar', f'{self.decompress_flag}xf', '-'])
        if self.strip:
            self.install_context.strip_exes(self.strip)

        self.install_context.run_script(self.s3_path, self.after_stage_script)

    def verify(self) -> bool:
        if not super().verify():
            return False
        self.stage()
        return self.install_context.compare_against_staging(self.untar_dir, self.install_path)

    def install(self) -> bool:
        if not super().install():
            return False
        self.stage()
        if self.subdir:
            self.install_context.make_subdir(self.subdir)
        elif self.install_path:
            self.install_context.make_subdir(self.install_path)

        self.install_context.move_from_staging(self.untar_dir, self.install_path)
        return True

    def __repr__(self) -> str:
        return f'S3TarballInstallable({self.name}, {self.install_path})'


class NightlyInstallable(Installable):
    def __init__(self, install_context: InstallationContext, config: Dict[str, Any]):
        super().__init__(install_context, config)
        self.subdir = self.config_get("subdir", "")
        self.strip = self.config_get('strip', False)
        compiler_name = self.config_get('compiler_name', f'{self.context[-1]}-{self.target_name}')
        current = s3_available_compilers()
        if compiler_name not in current:
            raise RuntimeError(f'Unable to find nightlies for {compiler_name}')
        most_recent = max(current[compiler_name])
        self.info(f'Most recent {compiler_name} is {most_recent}')
        self.s3_path = f'{compiler_name}-{most_recent}'
        self.install_path = os.path.join(self.subdir, f'{compiler_name}-{most_recent}')
        self.compiler_pattern = os.path.join(self.subdir, f'{compiler_name}-*')
        self.path_name_symlink = self.config_get('symlink', os.path.join(self.subdir, f'{compiler_name}'))
        self.num_to_keep = self.config_get('num_to_keep', 5)
        self._setup_check_exe(self.install_path)
        self._setup_check_link(self.s3_path, self.path_name_symlink)

    def stage(self) -> None:
        self.install_context.clean_staging()
        self.install_context.fetch_s3_and_pipe_to(f'{self.s3_path}.tar.xz', ['tar', 'Jxf', '-'])
        if self.strip:
            self.install_context.strip_exes(self.strip)
        self.install_context.run_script(os.path.join(self.install_context.staging, self.s3_path),
                                        self.after_stage_script)

    def verify(self) -> bool:
        if not super().verify():
            return False
        self.stage()
        return self.install_context.compare_against_staging(self.s3_path, self.install_path)

    def should_install(self) -> bool:
        return True

    def install(self) -> bool:
        if not super().install():
            return False
        self.stage()

        # Do this first, and add one for the file we haven't yet installed... (then dry run works)
        num_to_keep = self.num_to_keep + 1
        all_versions = list(sorted(self.install_context.glob(self.compiler_pattern)))
        for to_remove in all_versions[:-num_to_keep]:
            self.install_context.remove_dir(to_remove)

        self.install_context.move_from_staging(self.s3_path, self.install_path)
        self.install_context.set_link(Path(self.s3_path), self.path_name_symlink)

        return True

    def __repr__(self) -> str:
        return f'NightlyInstallable({self.name}, {self.install_path})'


class TarballInstallable(Installable):
    def __init__(self, install_context: InstallationContext, config: Dict[str, Any]):
        super().__init__(install_context, config)
        self.install_path = self.config_get('dir')
        self.install_path_symlink = self.config_get('symlink', False)
        self.untar_path = self.config_get('untar_dir', self.install_path)
        if self.config_get('create_untar_dir', False):
            self.untar_to = self.untar_path
        else:
            self.untar_to = '.'
        self.url = self.config_get('url')
        if self.config_get('compression') == 'xz':
            decompress_flag = 'J'
        elif self.config_get('compression') == 'gz':
            decompress_flag = 'z'
        elif self.config_get('compression') == 'bz2':
            decompress_flag = 'j'
        elif self.config_get('compression') == 'tar':
            decompress_flag = ''
        else:
            raise RuntimeError(f'Unknown compression {self.config_get("compression")}')
        self.configure_command = command_config(self.config_get('configure_command', []))
        self.tar_cmd = ['tar', f'{decompress_flag}xf', '-']
        strip_components = self.config_get("strip_components", 0)
        if strip_components:
            self.tar_cmd += ['--strip-components', str(strip_components)]
        extract_only = self.config_get("extract_only", "")
        if extract_only:
            self.tar_cmd += [extract_only]
        self.strip = self.config_get('strip', False)
        self._setup_check_exe(self.install_path)
        if self.install_path_symlink:
            self._setup_check_link(self.install_path, self.install_path_symlink)
        self.remove_older_pattern = self.config_get("remove_older_pattern", "")
        self.num_to_keep = self.config_get('num_to_keep', 5)

    def stage(self) -> None:
        self.install_context.clean_staging()
        self.install_context.fetch_url_and_pipe_to(f'{self.url}', self.tar_cmd, self.untar_to)
        if self.configure_command:
            self.install_context.stage_command(self.configure_command)
        if self.strip:
            self.install_context.strip_exes(self.strip)
        if not (self.install_context.staging / self.untar_path).is_dir():
            raise RuntimeError(f"After unpacking, {self.untar_path} was not a directory")
        self.install_context.run_script(self.install_context.staging / self.untar_to, self.after_stage_script)

    def verify(self) -> bool:
        if not super().verify():
            return False
        self.stage()
        return self.install_context.compare_against_staging(self.untar_path, self.install_path)

    def install(self) -> bool:
        if not super().install():
            return False
        self.stage()

        if self.remove_older_pattern:
            # Do this first, and add one for the file we haven't yet installed... (then dry run works)
            num_to_keep = self.num_to_keep + 1
            all_versions = list(sorted(self.install_context.glob(self.remove_older_pattern)))
            for to_remove in all_versions[:-num_to_keep]:
                self.install_context.remove_dir(to_remove)

        self.install_context.move_from_staging(self.untar_path, self.install_path)
        if self.install_path_symlink:
            self.install_context.set_link(self.install_path, self.install_path_symlink)
        return True

    def __repr__(self) -> str:
        return f'TarballInstallable({self.name}, {self.install_path})'


class RestQueryTarballInstallable(TarballInstallable):
    def __init__(self, install_context: InstallationContext, config: Dict[str, Any]):
        super().__init__(install_context, config)
        document = self.install_context.fetch_rest_query(self.config_get('url'))
        # pylint: disable=eval-used
        self.url = eval(self.config_get('query'), {}, dict(document=document))
        if not self.url:
            self.warn('No installation candidate found')
        else:
            self.info(f'resolved to {self.url}')

    def should_install(self) -> bool:
        if not self.url:
            return False
        return super().should_install()

    def __repr__(self) -> str:
        return f'RestQueryTarballInstallable({self.name}, {self.install_path})'


class ScriptInstallable(Installable):
    def __init__(self, install_context: InstallationContext, config: Dict[str, Any]):
        super().__init__(install_context, config)
        self.install_path = self.config_get('dir')
        self.install_path_symlink = self.config_get('symlink', False)
        self.fetch = self.config_get('fetch')
        self.script = self.config_get('script')
        self.strip = self.config_get('strip', False)
        self._setup_check_exe(self.install_path)
        if self.install_path_symlink:
            self._setup_check_link(self.install_path, self.install_path_symlink)

    def stage(self) -> None:
        self.install_context.clean_staging()
        for url in self.fetch:
            url, filename = url.split(' ')
            if url[:1] == '/':
                shutil.copyfile(url, self.install_context.staging / filename)
            else:
                with (self.install_context.staging / filename).open('wb') as f:
                    self.install_context.fetch_to(url, f)
            self.info(f'{url} -> {filename}')
        self.install_context.stage_command(['bash', '-c', self.script])
        if self.strip:
            self.install_context.strip_exes(self.strip)

    def verify(self) -> bool:
        if not super().verify():
            return False
        self.stage()
        return self.install_context.compare_against_staging(self.install_path)

    def install(self) -> bool:
        if not super().install():
            return False
        self.stage()
        self.install_context.move_from_staging(self.install_path)
        if self.install_path_symlink:
            self.install_context.set_link(self.install_path, self.install_path_symlink)
        return True

    def __repr__(self) -> str:
        return f'ScriptInstallable({self.name}, {self.install_path})'


@functools.lru_cache(maxsize=512)
def s3_available_rust_artifacts(prefix):
    dist_prefix = "dist/"
    return [compiler[len(dist_prefix):] for compiler in list_s3_artifacts('static-rust-lang-org', dist_prefix + prefix)
            if compiler.endswith('.tar.gz')]


class RustInstallable(Installable):
    def __init__(self, install_context: InstallationContext, config: Dict[str, Any]):
        super().__init__(install_context, config)
        self.install_path = self.config_get('dir')
        self._setup_check_exe(self.install_path)
        self.base_package = self.config_get('base_package')
        self.nightly_install_days = self.config_get('nightly_install_days', 0)

    def do_rust_install(self, component: str, install_to: Path) -> None:
        url = f'https://static.rust-lang.org/dist/{component}.tar.gz'
        untar_to = self.install_context.staging / '__temp_install__'
        self.install_context.fetch_url_and_pipe_to(url, ['tar', 'zxf', '-', '--strip-components=1'], untar_to)
        self.install_context.stage_command(
            ['./install.sh', f'--prefix={install_to}', '--verbose', '--without=rust-docs'], cwd=untar_to)
        self.install_context.remove_dir(untar_to)

    def stage(self) -> None:
        self.install_context.clean_staging()
        arch_std_prefix = f'rust-std-{self.target_name}-'
        suffix = '.tar.gz'
        architectures = [artifact[len(arch_std_prefix):-len(suffix)] for artifact in
                         s3_available_rust_artifacts(arch_std_prefix)]
        self.info(f"Installing for these architectures: {', '.join(architectures or ['none'])}")
        base_path = self.install_context.staging / f'rust-{self.target_name}'
        self.do_rust_install(self.base_package, base_path)
        for architecture in architectures:
            self.do_rust_install(f'rust-std-{self.target_name}-{architecture}', base_path)
        for binary in (b for b in (base_path / 'bin').glob('*') if self.install_context.is_elf(b)):
            self.install_context.set_rpath(binary, '$ORIGIN/../lib')
        for shared_object in (base_path / 'lib').glob("*.so"):
            self.install_context.set_rpath(shared_object, '$ORIGIN')
        self.install_context.remove_dir(base_path / 'share')

    def should_install(self) -> bool:
        if self.nightly_install_days > 0:
            dest_dir = self.install_context.destination / self.install_path
            if os.path.exists(dest_dir):
                dtime = datetime.fromtimestamp(dest_dir.stat().st_mtime)
                # The fudge factor of 30m is to sort of account for the installation time. Else
                # we start up the same time the next day and we get a 23hr58 minute old build and we
                # don't reinstall.
                age = datetime.now() - dtime + timedelta(minutes=30)
                self.info(f"Nightly build {dest_dir} is {age} old")
                if age.days > self.nightly_install_days:
                    return True
        return super().should_install()

    def verify(self) -> bool:
        if not super().verify():
            return False
        self.stage()
        return self.install_context.compare_against_staging(self.install_path)

    def install(self) -> bool:
        if not super().install():
            return False
        self.stage()
        self.install_context.move_from_staging(self.install_path)
        return True

    def __repr__(self) -> str:
        return f'RustInstallable({self.name}, {self.install_path})'


class PipInstallable(Installable):
    MV_URL = 'https://raw.githubusercontent.com/brbsix/virtualenv-mv/master/virtualenv-mv'

    def __init__(self, install_context: InstallationContext, config: Dict[str, Any]):
        super().__init__(install_context, config)
        self.install_path = self.config_get('dir')
        self._setup_check_exe(self.install_path)
        self.package = self.config_get('package')
        self.python = self.config_get('python')

    def stage(self) -> None:
        self.install_context.clean_staging()
        venv = self.install_context.staging / self.install_path
        self.install_context.check_output([self.python, '-mvenv', str(venv)])
        self.install_context.check_output([str(venv / 'bin' / 'pip'), 'install', self.package])

    def verify(self) -> bool:
        if not super().verify():
            return False
        self.stage()
        return self.install_context.compare_against_staging(self.install_path)

    def install(self) -> bool:
        if not super().install():
            return False
        self.stage()
        mv_script = self.install_context.staging / 'virtualenv-mv'
        with mv_script.open('wb') as f:
            self.install_context.fetch_to(PipInstallable.MV_URL, f)
        mv_script.chmod(0o755)

        def mv_venv(source, dest):
            self.install_context.check_output([str(mv_script), str(source), str(dest)])

        self.install_context.move_from_staging(self.install_path, do_staging_move=mv_venv)
        return True

    def __repr__(self) -> str:
        return f'PipInstallable({self.name}, {self.install_path})'


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

    if 'if' in node:
        if isinstance(node['if'], list):
            condition = set(node['if'])
        else:
            condition = {node['if']}
        if set(enabled).intersection(condition) != condition:
            return

    context = context[:]
    if name:
        context.append(name)
    base_config = dict(base_config)
    for key, value in node.items():
        if key != 'targets' and is_value_type(value):
            base_config[key] = value

    for child_name, child in node.items():
        for target in _targets_from(child, enabled, context, child_name, base_config):
            yield target

    if 'targets' in node:
        base_config['context'] = context
        for target in node['targets']:
            if isinstance(target, float):
                raise RuntimeError(f"Target {target} was parsed as a float. Enclose in quotes")
            if isinstance(target, str):
                target = {'name': target}
            yield expand_target(ChainMap(target, base_config), context)


INSTALLER_TYPES = {
    'tarballs': TarballInstallable,
    'restQueryTarballs': RestQueryTarballInstallable,
    's3tarballs': S3TarballInstallable,
    'nightly': NightlyInstallable,
    'script': ScriptInstallable,
    'github': GitHubInstallable,
    'gitlab': GitLabInstallable,
    'bitbucket': BitbucketInstallable,
    'rust': RustInstallable,
    'pip': PipInstallable
}


def installers_for(install_context, nodes, enabled):
    for target in targets_from(nodes, enabled,
                               dict(staging=install_context.staging, destination=install_context.destination,
                                    yaml_dir=install_context.yaml_dir, now=datetime.now())):
        assert 'type' in target
        target_type = target['type']
        if target_type not in INSTALLER_TYPES:
            raise RuntimeError(f'Unknown installer type {target_type}')
        installer_type = INSTALLER_TYPES[target_type]
        yield installer_type(install_context, target)
