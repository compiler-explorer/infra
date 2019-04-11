#!/usr/bin/env python3
# coding=utf-8
import glob
import os
import sys
import shutil
import tempfile
from argparse import ArgumentParser
from cachecontrol import CacheControl
from cachecontrol.caches.file_cache import FileCache
import subprocess
import yaml
import requests
import logging
import logging.config

logger = logging.getLogger(__name__)


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
        shutil.rmtree(self.staging, ignore_errors=True)
        subprocess.check_call(["rm", "-rf", self.staging])
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

    def move_from_staging(self, source, dest=None):
        if not dest:
            dest = source
        existing_dir_rename = os.path.join(self.staging, dest + ".orig")
        source = os.path.join(self.staging, source)
        dest = os.path.join(self.destination, dest)
        if self.dry_run:
            self.info(f'Would install {source} to {dest} but in dry-run mode')
            return
        self.info(f'Moving from staging ({source}) to final destination ({dest})')
        state = ''
        if os.path.isdir(dest):
            self.info(f'Destination exists, temporarily moving out of the way (to {existing_dir_rename}')
            os.rename(dest, existing_dir_rename)
            state = 'old_renamed'
        try:
            os.rename(source, dest)
            if state == 'old_renamed':
                state = 'old_needs_remove'
        finally:
            if state == 'old_needs_remove':
                self.debug(f'Removing temporarily moved {existing_dir_rename}')
                shutil.rmtree(existing_dir_rename, ignore_errors=True)
            elif state == 'old_renamed':
                self.warn(f'Moving old destination back')
                os.rename(existing_dir_rename, dest)

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
    def __init__(self, context, name, depends):
        self.context = context
        self.name = name
        if not depends:
            depends = []
        self.depends = depends

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


class S3TarballInstallable(Installable):
    def __init__(self, context, name, config, depends=None):
        super(S3TarballInstallable, self).__init__(context, name, depends)
        self.suffix = '.tar.xz'
        self.path_name = config['path_name']
        if config['compression'] == 'xz':
            self.suffix = '.tar.xz'
            self.decompress_flag = 'J'
        elif config['compression'] == 'gz':
            self.suffix = '.tar.gz'
            self.decompress_flag = 'z'
        else:
            raise RuntimeError(f'Unknown compression {config["compression"]}')
        self.strip = config['strip']
        self.check_call = config['check_exe'][:]
        self.check_call[0] = os.path.join(self.path_name, self.check_call[0])

    def stage(self):
        self.context.clean_staging()
        self.context.fetch_s3_and_pipe_to(f'{self.path_name}{self.suffix}', ['tar', f'{self.decompress_flag}xf', '-'])
        if self.strip:
            self.context.strip_exes()

    def verify(self):
        if not super(S3TarballInstallable, self).verify():
            return False
        self.stage()
        return self.context.compare_against_staging(self.path_name)

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
        self.context.move_from_staging(self.path_name)
        return True

    def __repr__(self) -> str:
        return f'S3TarballInstallable({self.name}, {self.path_name})'


class TarballInstallable(Installable):
    def __init__(self, context, name, config, depends=None):
        super(TarballInstallable, self).__init__(context, name, depends)
        self.path_name = config['dir']
        self.url = config['url']
        if config['compression'] == 'xz':
            self.decompress_flag = 'J'
        elif config['compression'] == 'gz':
            self.decompress_flag = 'z'
        else:
            raise RuntimeError(f'Unknown compression {config["compression"]}')
        self.strip = config['strip']
        self.check_call = config['check_exe'][:]
        self.check_call[0] = os.path.join(self.path_name, self.check_call[0])

    def stage(self):
        self.context.clean_staging()
        self.context.fetch_url_and_pipe_to(f'{self.url}', ['tar', f'{self.decompress_flag}xf', '-'])

    def verify(self):
        if not super(TarballInstallable, self).verify():
            return False
        self.stage()
        return self.context.compare_against_staging(self.path_name)

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
        self.context.move_from_staging(self.path_name)
        return True

    def __repr__(self) -> str:
        return f'TarballInstallable({self.name}, {self.path_name})'


def nodes_from(name, node_context, nodes):
    if isinstance(nodes, list):
        for node in nodes:
            yield (name, node_context, node)
    else:
        for name, node in nodes.items():
            yield (name, f'{node_context}/{name}', node)


def parse(install_context, installables, name, context, nodes):
    for name, node_context, node in nodes_from(name, context, nodes):
        if 'type' not in node:
            return parse(install_context, installables, name, node_context, node)
        type = node['type']
        if type == 's3tarballs':
            base_config = {
                'check_exe': node['check_exe'].split(" "),
                'strip': node.get('strip', False),
                'compression': node.get('compression', 'xz')
            }
            for config in node['targets']:
                if isinstance(config, str):
                    config = {'name': config}
                config['path_name'] = f'{name}-{config["name"]}'
                config = dict(base_config, **config)
                installables.append(
                    S3TarballInstallable(install_context, f'{node_context} {config["name"]}', config))
        elif type == 'tarballs':
            base_config = {
                'dir': node['dir'],
                'url': node['url'],
                'compression': node['compression'],
                'check_exe': node['check_exe'].split(" "),
                'strip': node.get('strip', False)
            }
            for config in node['targets']:
                config = dict(base_config, **config)
                for key in config.keys():
                    if isinstance(config[key], str):
                        config[key] = config[key].format(**config)
                installables.append(
                    TarballInstallable(install_context, f'{node_context} {config["name"]}', config))
        else:
            raise RuntimeError(f'Bad type {type} for {node_context}')


def filter_match(filter, installable):
    return filter in installable.name


def main():
    parser = ArgumentParser(description='Install binaries, libraries and compilers for Compiler Explorer')
    parser.add_argument('--dest', default='/opt/compiler-explorer', metavar='DEST',
                        help='install with DEST as the installation root (default %(default)s)')
    parser.add_argument('--staging-dir', default='/opt/compiler-explorer/staging', metavar='STAGEDIR',
                        help='install to STAGEDIR then rename in-place. Must be on the same drive as DEST for atomic'
                             'rename/replace. Directory will be removed during install (default %(default)s)')

    parser.add_argument('--s3_bucket', default='compiler-explorer', metavar='BUCKET',
                        help='look for S3 resources in BUCKET (default %(default)s)')
    parser.add_argument('--s3_dir', default='opt', metavar='DIR',
                        help='look for S3 resources in the bucket\'s subdirectory DIR (default %(default)s)')
    parser.add_argument('--yaml_dir', default=os.path.join(os.path.dirname(os.path.realpath(__file__)), 'yaml'),
                        help='look for installation yaml files in DIR (default %(default)s', metavar='DIR')
    parser.add_argument('--cache', metavar='DIR', help='cache requests at DIR')
    parser.add_argument('--dry_run', default=False, action='store_true', help='dry run only')
    parser.add_argument('--force', default=False, action='store_true', help='force even if would otherwise skip')

    parser.add_argument('--debug', default=False, action='store_true', help='log at debug')
    parser.add_argument('--log_to_console', default=False, action='store_true',
                        help='log output to console, even if logging to a file is requested')
    parser.add_argument('--log', metavar='LOGFILE', help='log to LOGFILE')

    parser.add_argument('command', choices=['list', 'install', 'check_installed', 'verify'], default='list',
                        nargs='?')
    parser.add_argument('filter', nargs='*', help='filter to apply', default=[])

    args = parser.parse_args()
    formatter = logging.Formatter(fmt='%(asctime)s %(name)-15s %(levelname)-8s %(message)s')
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG if args.debug else logging.INFO)
    if args.log:
        file_handler = logging.FileHandler(args.log)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    if not args.log or args.log_to_console:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

    s3_url = f'https://s3.amazonaws.com/{args.s3_bucket}/{args.s3_dir}'
    context = InstallationContext(args.dest, args.staging_dir, s3_url, args.dry_run, args.cache)

    installables = []
    for yamlfile in glob.glob(os.path.join(args.yaml_dir, '*.yaml')):
        parse(context, installables, "", "", yaml.load(open(yamlfile, 'r'), Loader=yaml.BaseLoader))

    for filt in args.filter:
        installables = filter(lambda installable: filter_match(filt, installable), installables)

    if args.command == 'list':
        print("Installation candidates:")
        for installable in sorted(installables, key=lambda x: x.name):
            print(installable.name)
        sys.exit(0)
    elif args.command == 'verify':
        num_ok = 0
        num_not_ok = 0
        for installable in installables:
            print(f"Checking {installable.name}")
            if not installable.is_installed():
                context.info(f"{installable.name} is not installed")
                num_not_ok += 1
            elif not installable.verify():
                context.info(f"{installable.name} is not OK")
                num_not_ok += 1
            else:
                num_ok += 1
        print(f'{num_ok} packages OK, {num_not_ok} not OK or not installed')
        if num_not_ok:
            sys.exit(1)
        sys.exit(0)
    elif args.command == 'check_installed':
        for installable in installables:
            if installable.is_installed():
                print(f"{installable.name}: installed")
            else:
                print(f"{installable.name}: not installed")
        sys.exit(0)
    elif args.command == 'install':
        num_installed = 0
        num_skipped = 0
        num_failed = 0
        for installable in installables:
            print(f"Installing {installable.name}")
            if installable.is_installed() and not args.force:
                context.info(f"{installable.name} is already installed, skipping")
                num_skipped += 1
            else:
                try:
                    if installable.install():
                        if not installable.is_installed():
                            context.error(f"{installable.name} installed OK, but doesn't appear as installed after")
                            num_failed += 1
                        else:
                            context.info(f"{installable.name} installed OK")
                            num_installed += 1
                    else:
                        context.info(f"{installable.name} failed to install")
                        num_failed += 1
                except Exception:
                    context.info(f"{installable.name} failed to install")
                    num_failed += 1
        print(f'{num_installed} packages installed OK, {num_skipped} skipped, and {num_failed} failed installation')
        if num_failed:
            sys.exit(1)
        sys.exit(0)
    else:
        raise RuntimeError("Er, whoops")


if __name__ == '__main__':
    main()
