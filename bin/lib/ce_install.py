#!/usr/bin/env python3
# coding=utf-8
import glob
import os
import sys
from argparse import ArgumentParser
import yaml
import logging
import logging.config

from lib.installation import InstallationContext, installers_for

logger = logging.getLogger(__name__)


def filter_match(filter, installable):
    return filter in installable.name


def main():
    parser = ArgumentParser(description='Install binaries, libraries and compilers for Compiler Explorer')
    parser.add_argument('--dest', default='/opt/compiler-explorer', metavar='DEST',
                        help='install with DEST as the installation root (default %(default)s)')
    parser.add_argument('--staging-dir', default='/opt/compiler-explorer/staging', metavar='STAGEDIR',
                        help='install to STAGEDIR then rename in-place. Must be on the same drive as DEST for atomic'
                             'rename/replace. Directory will be removed during install (default %(default)s)')

    parser.add_argument('--enable', nargs='*', default=[], metavar='TYPE',
                        help='enable targets of type TYPE (e.g. "nightly")')
    parser.add_argument('--s3_bucket', default='compiler-explorer', metavar='BUCKET',
                        help='look for S3 resources in BUCKET (default %(default)s)')
    parser.add_argument('--s3_dir', default='opt', metavar='DIR',
                        help='look for S3 resources in the bucket\'s subdirectory DIR (default %(default)s)')
    parser.add_argument('--yaml_dir', default=os.path.join(os.path.dirname(os.path.realpath(__file__)), '..', 'yaml'),
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
        for installer in installers_for(context, yaml.load(open(yamlfile, 'r'), Loader=yaml.BaseLoader), args.enable):
            installables.append(installer)

    for filt in args.filter:
        installables = filter(lambda installable: filter_match(filt, installable), installables)

    if args.command == 'list':
        print("Installation candidates:")
        for installable in sorted(installables, key=lambda x: x.name):
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
                except Exception as e:
                    context.info(f"{installable.name} failed to install: {e}")
                    num_failed += 1
        print(f'{num_installed} packages installed OK, {num_skipped} skipped, and {num_failed} failed installation')
        if num_failed:
            sys.exit(1)
        sys.exit(0)
    else:
        raise RuntimeError("Er, whoops")


if __name__ == '__main__':
    main()
