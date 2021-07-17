#!/usr/bin/env python3
# coding=utf-8
import glob
import logging
import logging.config
import os
import sys
import traceback
from argparse import ArgumentParser
from pathlib import Path

import yaml

from lib.amazon_properties import get_properties_compilers_and_libraries
from lib.config_safe_loader import ConfigSafeLoader
from lib.installation import InstallationContext, installers_for, Installable

logger = logging.getLogger(__name__)


def _context_match(context_query: str, installable: Installable) -> bool:
    context = context_query.split('/')
    root_only = context[0] == ''
    if root_only:
        context = context[1:]
        return installable.context[:len(context)] == context

    for sub in range(0, len(installable.context) - len(context) + 1):
        if installable.context[sub:sub + len(context)] == context:
            return True
    return False


def _target_match(target: str, installable: Installable) -> bool:
    return target == installable.target_name


def filter_match(filter_query: str, installable: Installable) -> bool:
    split = filter_query.split(' ', 1)
    if len(split) == 1:
        # We don't know if this is a target or context, so either work
        return _context_match(split[0], installable) or _target_match(split[0], installable)
    return _context_match(split[0], installable) and _target_match(split[1], installable)


def main():
    parser = ArgumentParser(prog='ce_install',
                            description='Install binaries, libraries and compilers for Compiler Explorer')
    parser.add_argument('--dest', default=Path('/opt/compiler-explorer'), metavar='DEST', type=Path,
                        help='install with DEST as the installation root (default %(default)s)')
    parser.add_argument('--image-dir', default=Path('/opt/squash-images'), metavar='IMAGES', type=Path,
                        help='build images to IMAGES (default %(default)s)')
    parser.add_argument('--staging-dir', default=Path('/opt/compiler-explorer/staging'), metavar='STAGEDIR', type=Path,
                        help='install to STAGEDIR then rename in-place. Must be on the same drive as DEST for atomic'
                             'rename/replace. Directory will be removed during install (default %(default)s)')

    parser.add_argument('--enable', action='append', default=[], metavar='TYPE',
                        help='enable targets of type TYPE (e.g. "nightly")')
    parser.add_argument('--s3_bucket', default='compiler-explorer', metavar='BUCKET',
                        help='look for S3 resources in BUCKET (default %(default)s)')
    parser.add_argument('--s3_dir', default='opt', metavar='DIR',
                        help='look for S3 resources in the bucket\'s subdirectory DIR (default %(default)s)')
    parser.add_argument('--yaml_dir', default=os.path.join(os.path.dirname(os.path.realpath(__file__)), '..', 'yaml'),
                        help='look for installation yaml files in DIR (default %(default)s', metavar='DIR')
    parser.add_argument('--cache', metavar='DIR', help='cache requests at DIR', type=Path)
    parser.add_argument('--dry_run', default=False, action='store_true', help='dry run only')
    parser.add_argument('--force', default=False, action='store_true', help='force even if would otherwise skip')

    parser.add_argument('--debug', default=False, action='store_true', help='log at debug')
    parser.add_argument('--log_to_console', default=False, action='store_true',
                        help='log output to console, even if logging to a file is requested')
    parser.add_argument('--log', metavar='LOGFILE', help='log to LOGFILE')

    parser.add_argument('--buildfor', default='', metavar='BUILDFOR',
                        help='filter to only build for given compiler (should be a CE compiler identifier), leave empty to build for all')

    parser.add_argument('command',
                        choices=['list', 'install', 'check_installed', 'verify', 'amazoncheck', 'build', 'squash'],
                        default='list',
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
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

    s3_url = f'https://s3.amazonaws.com/{args.s3_bucket}/{args.s3_dir}'
    context = InstallationContext(args.dest, args.staging_dir, s3_url, args.dry_run, 'nightly' in args.enable,
                                  args.cache, args.yaml_dir)

    installables = []
    for yamlfile in glob.glob(os.path.join(args.yaml_dir, '*.yaml')):
        for installer in installers_for(context, yaml.load(open(yamlfile, 'r'), Loader=ConfigSafeLoader), args.enable):
            installables.append(installer)

    installables_by_name = {installable.name: installable for installable in installables}
    for installable in installables:
        installable.link(installables_by_name)

    for filt in args.filter:
        def make_f(x=filt):  # see https://stupidpythonideas.blogspot.com/2016/01/for-each-loops-should-define-new.html
            return lambda installable: filter_match(x, installable)

        installables = filter(make_f(), installables)
    installables = sorted(installables, key=lambda x: x.sort_key)

    if args.command == 'list':
        print("Installation candidates:")
        for installable in installables:
            print(installable.name)
            logger.debug(installable)
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
    elif args.command == 'amazoncheck':
        logger.debug('Starting Amazon Check')
        languages = ['c', 'c++', 'd', 'cuda']

        for language in languages:
            logger.info('Checking %s libraries', language)
            [_, libraries] = get_properties_compilers_and_libraries(language, logger)

            for libraryid in libraries:
                logger.debug('Checking %s', libraryid)
                for version in libraries[libraryid]['versionprops']:
                    includepaths = libraries[libraryid]['versionprops'][version]['path']
                    for includepath in includepaths:
                        logger.debug('Checking for library %s %s: %s', libraryid, version, includepath)
                        if not os.path.exists(includepath):
                            logger.error('Path missing for library %s %s: %s', libraryid, version, includepath)
                        else:
                            logger.debug('Found path for library %s %s: %s', libraryid, version, includepath)

                    libpaths = libraries[libraryid]['versionprops'][version]['libpath']
                    for libpath in libpaths:
                        logger.debug('Checking for library %s %s: %s', libraryid, version, libpath)
                        if not os.path.exists(libpath):
                            logger.error('Path missing for library %s %s: %s', libraryid, version, libpath)
                        else:
                            logger.debug('Found path for library %s %s: %s', libraryid, version, libpath)
    elif args.command == 'squash':
        for installable in installables:
            if not installable.is_installed():
                context.warn(f"{installable.name} wasn't installed; skipping squash")
                continue
            destination: Path = args.image_dir / f"{installable.install_path}.img"
            if destination.exists() and not args.force:
                context.info(f"Skipping {installable.name} as it already exists at {destination}")
                continue
            context.info(f"Squashing {installable.name}  to {destination}")
            installable.squash_to(destination)
    elif args.command == 'install':
        num_installed = 0
        num_skipped = 0
        failed = []
        for installable in installables:
            print(f"Installing {installable.name}")
            if args.force or installable.should_install():
                try:
                    if installable.install():
                        if not installable.is_installed():
                            context.error(f"{installable.name} installed OK, but doesn't appear as installed after")
                            failed.append(installable.name)
                        else:
                            context.info(f"{installable.name} installed OK")
                            num_installed += 1
                    else:
                        context.info(f"{installable.name} failed to install")
                        failed.append(installable.name)
                except Exception as e:  # pylint: disable=broad-except
                    context.info(f"{installable.name} failed to install: {e}\n{traceback.format_exc(5)}")
                    failed.append(installable.name)
            else:
                context.info(f"{installable.name} is already installed, skipping")
                num_skipped += 1
        print(f'{num_installed} packages installed OK, {num_skipped} skipped, and {len(failed)} failed installation')
        if len(failed):
            print('Failed:')
            for f in sorted(failed):
                print(f'  {f}')
            sys.exit(1)
        sys.exit(0)
    elif args.command == 'build':
        num_installed = 0
        num_skipped = 0
        num_failed = 0
        for installable in installables:
            if args.buildfor:
                print(f"Building {installable.name} just for {args.buildfor}")
            else:
                print(f"Building {installable.name} for all")

            if args.force or installable.should_build():
                if not installable.is_installed():
                    context.info(f"{installable.name} is not installed, unable to build")
                    num_skipped += 1
                else:
                    try:
                        [num_installed, num_skipped, num_failed] = installable.build(args.buildfor)
                        if num_installed > 0:
                            context.info(f"{installable.name} built OK")
                        elif num_failed:
                            context.info(f"{installable.name} failed to build")
                    except RuntimeError as e:
                        if args.buildfor:
                            raise e
                        else:
                            context.info(f"{installable.name} failed to build: {e}")
                            num_failed += 1
            else:
                context.info(f"{installable.name} is already built, skipping")
                num_skipped += 1
        print(f'{num_installed} packages built OK, {num_skipped} skipped, and {num_failed} failed build')
        if num_failed:
            sys.exit(1)
        sys.exit(0)
    else:
        raise RuntimeError("Er, whoops")


if __name__ == '__main__':
    main()
