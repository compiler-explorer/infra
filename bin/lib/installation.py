import glob
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
from datetime import datetime
from collections import defaultdict, ChainMap
from pathlib import Path

import requests
from cachecontrol import CacheControl
from cachecontrol.caches import FileCache

from lib.amazon import list_compilers

VERSIONED_RE = re.compile(r'^(.*)-([0-9.]+)$')

MAX_ITERS = 5

NO_DEFAULT = "__no_default__"

logger = logging.getLogger(__name__)

_memoized_compilers = None


def s3_available_compilers():
    global _memoized_compilers
    if _memoized_compilers is None:
        _memoized_compilers = defaultdict(lambda: [])
        for compiler in list_compilers():
            match = VERSIONED_RE.match(compiler)
            if match:
                _memoized_compilers[match.group(1)].append(match.group(2))
    return _memoized_compilers


class InstallationContext(object):
    def __init__(self, destination, staging, s3_url, dry_run, cache):
        self.destination = destination
        self.staging = staging
        self.s3_url = s3_url
        self.dry_run = dry_run
        if cache:
            self.info(f"Using cache {cache}")
            self.fetcher = CacheControl(requests.session(), cache=FileCache(cache))
        else:
            self.info(f"Making uncached requests")
            self.fetcher = requests

    def debug(self, message):
        logger.debug(message)

    def info(self, message):
        logger.info(message)

    def warn(self, message):
        logger.warning(message)

    def error(self, message):
        logger.error(message)

    def clean_staging(self):
        self.debug(f"Cleaning staging dir {self.staging}")
        if os.path.isdir(self.staging):
            subprocess.check_call(["chmod", "-R", "u+w", self.staging])
            shutil.rmtree(self.staging, ignore_errors=True)
        self.debug(f"Recreating staging dir {self.staging}")
        os.makedirs(self.staging)

    def fetch_to(self, url, fd):
        self.debug(f'Fetching {url}')
        request = self.fetcher.get(url, stream=True)
        if not request.ok:
            self.error(f'Failed to fetch {url}: {request}')
            raise RuntimeError(f'Fetch failure for {url}: {request}')
        fetched = 0
        length = int(request.headers['content-length'])
        self.info(f'Fetching {url} ({length} bytes)')
        report_every_secs = 5
        report_time = time.time() + report_every_secs
        for chunk in request.iter_content(chunk_size=4 * 1024 * 1024):
            fd.write(chunk)
            fetched += len(chunk)
            now = time.time()
            if now >= report_time:
                self.info(f'{100.0 * fetched / length:.1f}% of {url}...')
                report_time = now + report_every_secs
        self.info(f'100% of {url}')
        fd.flush()

    def fetch_url_and_pipe_to(self, url, command, subdir='.'):
        untar_dir = os.path.join(self.staging, subdir)
        os.makedirs(untar_dir, exist_ok=True)
        # We stream to a temporary file first before then piping this to the command
        # as sometimes the command can take so long the URL endpoint closes the door on us
        with tempfile.TemporaryFile() as fd:
            self.fetch_to(url, fd)
            fd.seek(0)
            self.info(f'Piping to {" ".join(command)}')
            subprocess.check_call(command, stdin=fd, cwd=untar_dir)

    def stage_command(self, command):
        self.info(f'Staging with {" ".join(command)}')
        subprocess.check_call(command, cwd=self.staging)

    def fetch_s3_and_pipe_to(self, s3, command):
        return self.fetch_url_and_pipe_to(f'{self.s3_url}/{s3}', command)

    def make_subdir(self, subdir):
        full_subdir = Path(self.destination) / subdir
        full_subdir.mkdir(parents=True, exist_ok=True)

    def read_link(self, link):
        return os.readlink(os.path.join(self.destination, link))

    def set_link(self, source, dest):
        if self.dry_run:
            self.info(f'Would symlink {source} to {dest}')
            return

        full_dest = os.path.join(self.destination, dest)
        if os.path.exists(full_dest):
            os.remove(full_dest)
        self.info(f'Symlinking {dest} to {source}')
        os.symlink(source, full_dest)

    def glob(self, pattern):
        return [os.path.relpath(x, self.destination) for x in glob.glob(os.path.join(self.destination, pattern))]

    def remove_dir(self, directory):
        if self.dry_run:
            self.info(f'Would remove directory {directory} but in dry-run mode')
        else:
            shutil.rmtree(os.path.join(self.destination, directory), ignore_errors=True)
            self.info(f'Removing {directory}')

    def check_link(self, source, link):
        try:
            link = self.read_link(link)
            self.debug(f'readlink returned {link}')
            return link == source
        except FileNotFoundError:
            self.debug(f'File not found for {link}')
            return False

    def move_from_staging(self, source, dest=None):
        if not dest:
            dest = source
        existing_dir_rename = os.path.join(self.staging, "temp_orig")
        source = os.path.join(self.staging, source)
        dest = os.path.join(self.destination, dest)
        if self.dry_run:
            self.info(f'Would install {source} to {dest} but in dry-run mode')
            return
        self.info(f'Moving from staging ({source}) to final destination ({dest})')
        if not os.path.isdir(source):
            staging_contents = subprocess.check_output(['ls', '-l', self.staging]).decode('utf-8')
            self.info(f"Directory listing of staging:\n{staging_contents}")
            raise RuntimeError(f"Missing source '{source}'")
        # Some tar'd up GCCs are actually marked read-only...
        subprocess.check_call(["chmod", "u+w", source])
        state = ''
        if os.path.isdir(dest):
            self.info(f'Destination {dest} exists, temporarily moving out of the way (to {existing_dir_rename})')
            os.replace(dest, existing_dir_rename)
            state = 'old_renamed'
        try:
            os.replace(source, dest)
            if state == 'old_renamed':
                state = 'old_needs_remove'
        finally:
            if state == 'old_needs_remove':
                self.debug(f'Removing temporarily moved {existing_dir_rename}')
                shutil.rmtree(existing_dir_rename, ignore_errors=True)
            elif state == 'old_renamed':
                self.warn(f'Moving old destination back')
                os.replace(existing_dir_rename, dest)

    def compare_against_staging(self, source, dest=None):
        if not dest:
            dest = source
        source = os.path.join(self.staging, source)
        dest = os.path.join(self.destination, dest)
        self.info(f'Comparing {source} vs {dest}...')
        result = subprocess.call(['diff', '-r', source, dest])
        if result == 0:
            self.info('Contents match')
        else:
            self.warn('Contents differ')
        return result == 0

    def check_output(self, args, env=None):
        args = args[:]
        args[0] = os.path.join(self.destination, args[0])
        logger.debug('Executing %s in %s', args, self.destination)
        return subprocess.check_output(args, cwd=self.destination, env=env).decode('utf-8')

    def strip_exes(self, paths):
        if isinstance(paths, bool):
            if not paths:
                return
            paths = ['.']
        to_strip = []
        for path in paths:
            path = os.path.join(self.staging, path)
            logger.debug(f"Looking for executables to strip in {path}")
            if not os.path.isdir(path):
                raise RuntimeError(f"While looking for files to strip, {path} was not a directory")
            for dirpath, dirnames, filenames in os.walk(path):
                for filename in filenames:
                    full_path = os.path.join(dirpath, filename)
                    if os.access(full_path, os.X_OK):
                        to_strip.append(full_path)

        # Deliberately ignore errors
        subprocess.call(['strip'] + to_strip)


class Installable(object):
    def __init__(self, install_context, config):
        self.install_context = install_context
        self.config = config
        self.target_name = self.config.get("name", "(unnamed)")
        self.context = self.config_get("context", [])
        self.name = f'{"/".join(self.context)} {self.target_name}'
        self.depends = self.config.get('depends', [])
        self.install_always = self.config.get('install_always', False)
        self._check_link = None

    def _setup_check_exe(self, path_name):
        self.check_env = dict([x.replace('%PATH%', path_name).split('=', 1) for x in self.config_get('check_env', [])])

        self.check_file = self.config_get('check_file', False)
        if self.check_file:
            self.check_file = os.path.join(path_name, self.check_file)
        else:
            self.check_call = command_config(self.config_get('check_exe'))
            self.check_call[0] = os.path.join(path_name, self.check_call[0])

    def _setup_check_link(self, source, link):
        self._check_link = lambda: self.install_context.check_link(source, link)

    def debug(self, message):
        self.install_context.debug(f'{self.name}: {message}')

    def info(self, message):
        self.install_context.info(f'{self.name}: {message}')

    def warn(self, message):
        self.install_context.warn(f'{self.name}: {message}')

    def error(self, message):
        self.install_context.error(f'{self.name}: {message}')

    def verify(self):
        return True

    def should_install(self):
        return self.install_always or not self.is_installed()

    def install(self):
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

    def install_internal(self):
        raise RuntimeError("needs to be implemented")

    def is_installed(self):
        if self._check_link and not self._check_link():
            self.debug('Check link returned false')
            return False

        if self.check_file:
            res = os.path.isfile(os.path.join(self.install_context.destination, self.check_file))
            self.debug(f'Check file for "{self.check_file}" returned {res}')
            return res

        try:
            res = self.install_context.check_output(self.check_call, env=self.check_env)
            self.debug(f'Check call returned {res}')
            return True
        except FileNotFoundError:
            self.debug(f'File not found for {self.check_call}')
            return False
        except subprocess.CalledProcessError:
            self.debug(f'Got an error for {self.check_call}')
            return False

    def config_get(self, config_key, default=None):
        if config_key not in self.config and default is None:
            raise RuntimeError(f"Missing required key '{config_key}' in {self.name}")
        return self.config.get(config_key, default)


def command_config(config):
    if isinstance(config, str):
        return config.split(" ")
    return config


class S3TarballInstallable(Installable):
    def __init__(self, install_context, config):
        super(S3TarballInstallable, self).__init__(install_context, config)
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
        self.path_name = self.config_get('path_name', default_path_name)
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
        self._setup_check_exe(self.path_name)

    def stage(self):
        self.install_context.clean_staging()
        self.install_context.fetch_s3_and_pipe_to(self.s3_path, ['tar', f'{self.decompress_flag}xf', '-'])
        if self.strip:
            self.install_context.strip_exes(self.strip)

    def verify(self):
        if not super(S3TarballInstallable, self).verify():
            return False
        self.stage()
        return self.install_context.compare_against_staging(self.untar_dir, self.path_name)

    def install(self):
        if not super(S3TarballInstallable, self).install():
            return False
        self.stage()
        if self.subdir:
            self.install_context.make_subdir(self.subdir)
        self.install_context.move_from_staging(self.untar_dir, self.path_name)
        return True

    def __repr__(self) -> str:
        return f'S3TarballInstallable({self.name}, {self.path_name})'


class NightlyInstallable(Installable):
    def __init__(self, install_context, config):
        super(NightlyInstallable, self).__init__(install_context, config)
        self.subdir = self.config_get("subdir", "")
        self.strip = self.config_get('strip', False)
        compiler_name = self.config_get('compiler_name', f'{self.context[-1]}-{self.target_name}')
        current = s3_available_compilers()
        if compiler_name not in current:
            raise RuntimeError(f'Unable to find nightlies for {compiler_name}')
        most_recent = max(current[compiler_name])
        self.info(f'Most recent {compiler_name} is {most_recent}')
        self.s3_path = f'{compiler_name}-{most_recent}'
        self.path_name = os.path.join(self.subdir, f'{compiler_name}-{most_recent}')
        self.compiler_pattern = os.path.join(self.subdir, f'{compiler_name}-*')
        self.path_name_symlink = self.config_get('symlink', os.path.join(self.subdir, f'{compiler_name}'))
        self.num_to_keep = self.config_get('num_to_keep', 5)
        self._setup_check_exe(self.path_name)
        self._setup_check_link(self.s3_path, self.path_name_symlink)

    def stage(self):
        self.install_context.clean_staging()
        self.install_context.fetch_s3_and_pipe_to(f'{self.s3_path}.tar.xz', ['tar', f'Jxf', '-'])
        if self.strip:
            self.install_context.strip_exes(self.strip)

    def verify(self):
        if not super(NightlyInstallable, self).verify():
            return False
        self.stage()
        return self.install_context.compare_against_staging(self.s3_path, self.path_name)

    def should_install(self):
        return True

    def install(self):
        if not super(NightlyInstallable, self).install():
            return False
        self.stage()

        # Do this first, and add one for the file we haven't yet installed... (then dry run works)
        num_to_keep = self.num_to_keep + 1
        all_versions = list(sorted(self.install_context.glob(self.compiler_pattern)))
        for to_remove in all_versions[:-num_to_keep]:
            self.install_context.remove_dir(to_remove)

        self.install_context.move_from_staging(self.s3_path, self.path_name)
        self.install_context.set_link(self.s3_path, self.path_name_symlink)

        return True

    def __repr__(self) -> str:
        return f'NightlyInstallable({self.name}, {self.path_name})'


class TarballInstallable(Installable):
    def __init__(self, install_context, config):
        super(TarballInstallable, self).__init__(install_context, config)
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
        else:
            raise RuntimeError(f'Unknown compression {self.config_get("compression")}')
        self.configure_command = command_config(self.config_get('configure_command', []))
        self.tar_cmd = ['tar', f'{decompress_flag}xf', '-']
        strip_components = self.config_get("strip_components", 0)
        if strip_components:
            self.tar_cmd += ['--strip-components', str(strip_components)]
        self.strip = self.config_get('strip', False)
        self._setup_check_exe(self.install_path)
        if self.install_path_symlink:
            self._setup_check_link(self.install_path, self.install_path_symlink)

    def stage(self):
        self.install_context.clean_staging()
        self.install_context.fetch_url_and_pipe_to(f'{self.url}', self.tar_cmd, self.untar_to)
        if self.configure_command:
            self.install_context.stage_command(self.configure_command)
        if self.strip:
            self.install_context.strip_exes(self.strip)
        if not os.path.isdir(os.path.join(self.install_context.staging, self.untar_path)):
            raise RuntimeError(f"After unpacking, {self.untar_path} was not a directory")

    def verify(self):
        if not super(TarballInstallable, self).verify():
            return False
        self.stage()
        return self.install_context.compare_against_staging(self.untar_path, self.install_path)

    def install(self):
        if not super(TarballInstallable, self).install():
            return False
        self.stage()
        self.install_context.move_from_staging(self.untar_path, self.install_path)
        if self.install_path_symlink:
            self.install_context.set_link(self.install_path, self.install_path_symlink)
        return True

    def __repr__(self) -> str:
        return f'TarballInstallable({self.name}, {self.install_path})'


class ScriptInstallable(Installable):
    def __init__(self, install_context, config):
        super(ScriptInstallable, self).__init__(install_context, config)
        self.install_path = self.config_get('dir')
        self.install_path_symlink = self.config_get('symlink', False)
        self.fetch = self.config_get('fetch')
        self.script = self.config_get('script')
        self.strip = self.config_get('strip', False)
        self._setup_check_exe(self.install_path)
        if self.install_path_symlink:
            self._setup_check_link(self.install_path, self.install_path_symlink)

    def stage(self):
        self.install_context.clean_staging()
        for url in self.fetch:
            url, filename = url.split(' ')
            with open(os.path.join(self.install_context.staging, filename), 'wb') as f:
                self.install_context.fetch_to(url, f)
            self.info(f'{url} -> {filename}')
        self.install_context.stage_command(['bash', '-c', self.script])
        if self.strip:
            self.install_context.strip_exes(self.strip)

    def verify(self):
        if not super(ScriptInstallable, self).verify():
            return False
        self.stage()
        return self.install_context.compare_against_staging(self.install_path)

    def install(self):
        if not super(ScriptInstallable, self).install():
            return False
        self.stage()
        self.install_context.move_from_staging(self.install_path)
        if self.install_path_symlink:
            self.install_context.set_link(self.install_path, self.install_path_symlink)
        return True

    def __repr__(self) -> str:
        return f'ScriptInstallable({self.name}, {self.install_path})'


def targets_from(node, enabled, base_config=None):
    if base_config is None:
        base_config = {}
    return _targets_from(node, enabled, [], "", base_config)


def is_list_of_strings(value):
    return isinstance(value, list) and all(isinstance(x, str) for x in value)


def is_value_type(value):
    return isinstance(value, str) \
           or isinstance(value, bool) \
           or isinstance(value, float) \
           or isinstance(value, int) \
           or is_list_of_strings(value)


def needs_expansion(target):
    for value in target.values():
        if is_list_of_strings(value):
            for v in value:
                if '{' in v:
                    return True
        elif isinstance(value, str):
            if '{' in value:
                return True
    return False


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
        condition = node['if']
        if condition not in enabled:
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
            target = ChainMap(target, base_config)
            iterations = 0
            while needs_expansion(target):
                iterations += 1
                if iterations > MAX_ITERS:
                    raise RuntimeError(f"Too many mutual references (in {'/'.join(context)})")
                for key, value in target.items():
                    try:
                        if is_list_of_strings(value):
                            target[key] = [x.format(**target) for x in value]
                        elif isinstance(value, str):
                            target[key] = value.format(**target)
                        elif isinstance(value, float):
                            target[key] = str(value)
                    except KeyError as ke:
                        raise RuntimeError(f"Unable to find key {ke} in {target[key]} (in {'/'.join(context)})")
            yield target


INSTALLER_TYPES = {
    'tarballs': TarballInstallable,
    's3tarballs': S3TarballInstallable,
    'nightly': NightlyInstallable,
    'script': ScriptInstallable
}


def installers_for(install_context, nodes, enabled):
    for target in targets_from(nodes, enabled, {'staging': install_context.staging, 'now': datetime.now()}):
        assert 'type' in target
        target_type = target['type']
        if target_type not in INSTALLER_TYPES:
            raise RuntimeError(f'Unknown installer type {target_type}')
        installer_type = INSTALLER_TYPES[target_type]
        yield installer_type(install_context, target)
