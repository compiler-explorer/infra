import logging
import os
import re
import shutil
import subprocess
import tempfile
from collections import defaultdict

import requests
from cachecontrol import CacheControl
from cachecontrol.caches import FileCache

from lib.amazon import list_compilers

logger = logging.getLogger(__name__)

_memoized_compilers = None


def s3_available_compilers():
    global _memoized_compilers
    if _memoized_compilers is None:
        splitter = re.compile(r'^(.*)-([0-9.]+)$')
        _memoized_compilers = defaultdict(lambda: [])
        for compiler in list_compilers():
            match = splitter.match(compiler)
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
        for chunk in request.iter_content(chunk_size=4 * 1024 * 1024):
            fd.write(chunk)
            fetched += len(chunk)
            self.info(f'{100.0 * fetched / length:.1f}% of {url}...')
        fd.flush()

    def fetch_url_and_pipe_to(self, url, command):
        # We stream to a temporary file first before then piping this to the command
        # as sometimes the command can take so long the URL endpoint closes the door on us
        with tempfile.TemporaryFile() as fd:
            self.fetch_to(url, fd)
            fd.seek(0)
            self.info(f'Piping to {" ".join(command)}')
            subprocess.check_call(command, stdin=fd, cwd=self.staging)

    def fetch_s3_and_pipe_to(self, s3, command):
        return self.fetch_url_and_pipe_to(f'{self.s3_url}/{s3}', command)

    def make_subdir(self, subdir):
        full_subdir = os.path.join(self.destination, subdir)
        if not os.path.isdir(full_subdir):
            os.mkdir(full_subdir)

    def read_link(self, link):
        return os.readlink(os.path.join(self.destination, link))

    def set_link(self, source, dest):
        full_dest = os.path.join(self.destination, dest)
        if os.path.exists(full_dest):
            os.remove(full_dest)
        self.info(f'Symlinking {dest} to {source}')
        os.symlink(source, full_dest)

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

    def check_output(self, args):
        args = args[:]
        args[0] = os.path.join(self.destination, args[0])
        logger.debug('Executing %s', args)
        return subprocess.check_output(args).decode('utf-8')

    def strip_exes(self):
        to_strip = []
        for dirpath, dirnames, filenames in os.walk(self.staging):
            for filename in filenames:
                full_path = os.path.join(dirpath, filename)
                if os.stat(full_path).st_mode & 0o444:
                    to_strip.append(full_path)

        # Deliberately ignore errors
        subprocess.call(['strip'] + to_strip)


class Installable(object):
    def __init__(self, context, config):
        self.context = context
        self.name = f'{"/".join(config["context"])} {config["name"]}'
        self.depends = config.get('depends', [])

    def debug(self, message):
        self.context.debug(f'{self.name}: {message}')

    def info(self, message):
        self.context.info(f'{self.name}: {message}')

    def warn(self, message):
        self.context.warn(f'{self.name}: {message}')

    def error(self, message):
        self.context.error(f'{self.name}: {message}')

    def verify(self):
        return True

    def is_installed(self):
        raise RuntimeError("needs to be implemented")

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


def command_config(config):
    if isinstance(config, str):
        return config.split(" ")
    return config[0]


class S3TarballInstallable(Installable):
    def __init__(self, context, config):
        super(S3TarballInstallable, self).__init__(context, config)
        # todo config getter with needed/unneeded? or try/catch at top level to give decent errors if missing
        self.subdir = config.get("subdir", None)
        name = config["name"]
        if self.subdir:
            default_s3_path_prefix = f'{self.subdir}-{config["context"][-1]}-{name}'
            default_path_name = f'{self.subdir}/{config["context"][-1]}-{name}'
            default_untar_dir = f'{config["context"][-1]}-{name}'
        else:
            default_s3_path_prefix = f'{config["context"][-1]}-{name}'
            default_path_name = f'{config["context"][-1]}-{name}'
            default_untar_dir = default_path_name
        s3_path_prefix = config.get('s3_path_prefix', default_s3_path_prefix)
        self.path_name = config.get('path_name', default_path_name)
        self.untar_dir = config.get("untar_dir", default_untar_dir)
        compression = config.get('compression', 'xz')
        if compression == 'xz':
            self.s3_path = f'{s3_path_prefix}.tar.xz'
            self.decompress_flag = 'J'
        elif compression == 'gz':
            self.s3_path = f'{s3_path_prefix}.tar.gz'
            self.decompress_flag = 'z'
        else:
            raise RuntimeError(f'Unknown compression {compression}')
        self.strip = config.get('strip', False)
        self.check_call = command_config(config['check_exe'])
        self.check_call[0] = os.path.join(self.path_name, self.check_call[0])

    def stage(self):
        self.context.clean_staging()
        self.context.fetch_s3_and_pipe_to(self.s3_path, ['tar', f'{self.decompress_flag}xf', '-'])
        if self.strip:
            self.context.strip_exes()

    def verify(self):
        if not super(S3TarballInstallable, self).verify():
            return False
        self.stage()
        return self.context.compare_against_staging(self.untar_dir, self.path_name)

    def is_installed(self):
        try:
            res = self.context.check_output(self.check_call)
            self.debug(f'Check call returned {res}')
            return True
        except FileNotFoundError:
            self.debug(f'File not found for {self.check_call}')
            return False
        except subprocess.CalledProcessError:
            self.debug(f'Got an error for {self.check_call}')
            return False

    def install(self):
        if not super(S3TarballInstallable, self).install():
            return False
        self.stage()
        if self.subdir:
            self.context.make_subdir(self.subdir)
        self.context.move_from_staging(self.untar_dir, self.path_name)
        return True

    def __repr__(self) -> str:
        return f'S3TarballInstallable({self.name}, {self.path_name})'


class NightlyInstallable(Installable):
    def __init__(self, context, config):
        super(NightlyInstallable, self).__init__(context, config)
        self.strip = config.get('strip', False)
        compiler_name = f'{config["context"][-1]}-{config["name"]}'
        current = s3_available_compilers()
        if compiler_name not in current:
            raise RuntimeError(f'Unable to find nightlies for {compiler_name}')
        most_recent = max(current[compiler_name])
        self.context.info(f'Most recent {compiler_name} is {most_recent}')
        self.path_name = f'{compiler_name}-{most_recent}'
        self.path_name_symlink = f'{compiler_name}'
        self.check_call = command_config(config['check_exe'])
        self.check_call[0] = os.path.join(self.path_name, self.check_call[0])

    def stage(self):
        self.context.clean_staging()
        self.context.fetch_s3_and_pipe_to(f'{self.path_name}.tar.xz', ['tar', f'Jxf', '-'])
        if self.strip:
            self.context.strip_exes()

    def verify(self):
        if not super(NightlyInstallable, self).verify():
            return False
        self.stage()
        return self.context.compare_against_staging(self.path_name)

    def is_installed(self):
        try:
            link = self.context.read_link(self.path_name_symlink)
            self.debug(f'readlink returned {link}')
            if link != self.path_name:
                return False
            res = self.context.check_output(self.check_call)
            self.debug(f'Check call returned {res}')
            return True
        except OSError as e:
            self.debug(f'OS error {e} for {self.check_call}')
            return False
        except subprocess.CalledProcessError:
            self.debug(f'Got an error for {self.check_call}')
            return False

    def install(self):
        # TODO: remove older
        if not super(NightlyInstallable, self).install():
            return False
        self.stage()
        self.context.move_from_staging(self.path_name)
        self.context.set_link(self.path_name, self.path_name_symlink)
        return True

    def __repr__(self) -> str:
        return f'NightlyInstallable({self.name}, {self.path_name})'


class TarballInstallable(Installable):
    def __init__(self, context, config):
        super(TarballInstallable, self).__init__(context, config)
        self.install_path = config['dir']
        self.untar_path = config.get('untar_dir', self.install_path)
        self.url = config['url']
        if config['compression'] == 'xz':
            self.decompress_flag = 'J'
        elif config['compression'] == 'gz':
            self.decompress_flag = 'z'
        elif config['compression'] == 'bz2':
            self.decompress_flag = 'j'
        else:
            raise RuntimeError(f'Unknown compression {config["compression"]}')
        self.strip = config.get('strip', False)
        self.check_call = command_config(config['check_exe'])
        self.check_call[0] = os.path.join(self.install_path, self.check_call[0])

    def stage(self):
        self.context.clean_staging()
        self.context.fetch_url_and_pipe_to(f'{self.url}', ['tar', f'{self.decompress_flag}xf', '-'])
        if not os.path.isdir(os.path.join(self.context.staging, self.untar_path)):
            raise RuntimeError(f"After unpacking, {self.untar_path} was not a directory")

    def verify(self):
        if not super(TarballInstallable, self).verify():
            return False
        self.stage()
        return self.context.compare_against_staging(self.untar_path, self.install_path)

    def is_installed(self):
        try:
            res = self.context.check_output(self.check_call)
            self.debug(f'Check call returned {res}')
            return True
        except FileNotFoundError:
            self.debug(f'File not found for {self.check_call}')
            return False
        except subprocess.CalledProcessError:
            self.debug(f'Got an error for {self.check_call}')
            return False

    def install(self):
        if not super(TarballInstallable, self).install():
            return False
        self.stage()
        self.context.move_from_staging(self.untar_path, self.install_path)
        return True

    def __repr__(self) -> str:
        return f'TarballInstallable({self.name}, {self.install_path})'


def targets_from(node, enabled):
    return _targets_from(node, enabled, [], "", {})


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
        if isinstance(value, str):
            base_config[key] = value

    for child_name, child in node.items():
        for target in _targets_from(child, enabled, context, child_name, base_config):
            yield target

    if 'targets' in node:
        base_config['context'] = context
        for target in node['targets']:
            if isinstance(target, str):
                target = {'name': target}
            target = dict(base_config, **target)
            for key in target.keys():
                if isinstance(target[key], str):
                    target[key] = target[key].format(**target)
            yield target


INSTALLER_TYPES = {
    'tarballs': TarballInstallable,
    's3tarballs': S3TarballInstallable,
    'nightly': NightlyInstallable
}


def installers_for(install_context, nodes, enabled):
    for target in targets_from(nodes, enabled):
        assert 'type' in target
        target_type = target['type']
        if target_type not in INSTALLER_TYPES:
            raise RuntimeError(f'Unknown installer type {target_type}')
        installer_type = INSTALLER_TYPES[target_type]
        yield installer_type(install_context, target)
