#!/usr/bin/env python3
# coding=utf-8
import logging
import logging.config
import os
import sys
import traceback
from argparse import ArgumentParser, Namespace
from pathlib import Path

import yaml

from lib.amazon_properties import get_properties_compilers_and_libraries
from lib.config_safe_loader import ConfigSafeLoader
from lib.installation import InstallationContext, installers_for, Installable
from lib.library_yaml import LibraryYaml

_LOGGER = logging.getLogger(__name__)


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


def filter_aggregate(filters: list, installable: Installable, filter_match_all: bool = True) -> bool:
    # if there are no filters, accept it
    if not filters:
        return True

    # accept installable if it passes all filters (if filter_match_all is set) or any filters (otherwise)
    filter_generator = (filter_match(filt, installable) for filt in filters)
    return all(filter_generator) if filter_match_all else any(filter_generator)


def squash_mount_check(rootfolder, subdir, context):
    for filename in os.listdir(os.path.join(rootfolder, subdir)):
        if filename.endswith(".img"):
            checkdir = Path(os.path.join("/opt/compiler-explorer/", subdir, filename[:-4]))
            if not checkdir.exists():
                _LOGGER.error("Missing mount point %s", checkdir)
        else:
            if subdir == "":
                squash_mount_check(rootfolder, filename, context)
            else:
                squash_mount_check(rootfolder, f"{subdir}/{filename}", context)


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
    parser.add_argument('--resource_dir',
                        default=os.path.join(os.path.dirname(os.path.realpath(__file__)), '..', 'resources'),
                        help='look for installation resource files in DIR (default %(default)s', metavar='DIR')
    parser.add_argument('--yaml_dir', default=os.path.join(os.path.dirname(os.path.realpath(__file__)), '..', 'yaml'),
                        help='look for installation yaml files in DIR (default %(default)s', metavar='DIR')
    parser.add_argument('--cache', metavar='DIR', help='cache requests at DIR', type=Path)
    parser.add_argument('--dry_run', default=False, action='store_true', help='dry run only')
    parser.add_argument('--force', default=False, action='store_true', help='force even if would otherwise skip')
    parser.add_argument('--allow_unsafe_ssl', default=False, action='store_true',
                        help='skip ssl certificate checks on https connections')

    parser.add_argument('--debug', default=False, action='store_true', help='log at debug')
    parser.add_argument('--keep-staging', default=False, action='store_true', help='keep the unique staging directory')
    parser.add_argument('--log_to_console', default=False, action='store_true',
                        help='log output to console, even if logging to a file is requested')
    parser.add_argument('--log', metavar='LOGFILE', help='log to LOGFILE')

    parser.add_argument('--buildfor', default='', metavar='BUILDFOR',
                        help='filter to only build for given compiler (should be a CE compiler identifier), leave empty to build for all')
    parser.add_argument('--filter-match-all', default=True, action='store_true',
                        help='installables must pass all filters')
    parser.add_argument('--filter-match-any', default=False, action='store_false', dest='filter_match_all',
                        help='installables must pass any filter (default "False")')

    parser.add_argument('command',
                        choices=['list', 'install', 'check_installed', 'verify', 'amazoncheck', 'build', 'squash',
                                 'squashcheck', 'reformat', 'addtoprustcrates', 'generaterustprops', 'addcrate'],
                        default='list',
                        nargs='?')
    parser.add_argument('filter', nargs='*', help='filters to apply', default=[])

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
    _app(args, InstallationContext(args.dest, args.staging_dir, s3_url, args.dry_run, 'nightly' in args.enable,
                                   args.cache, args.yaml_dir, args.allow_unsafe_ssl, args.resource_dir,
                                   args.keep_staging))


def _app(args: Namespace, context: InstallationContext):
    installables = []
    for yaml_path in Path(args.yaml_dir).glob('*.yaml'):
        with yaml_path.open() as yaml_file:
            yaml_doc = yaml.load(yaml_file, Loader=ConfigSafeLoader)
        for installer in installers_for(context, yaml_doc, args.enable):
            installables.append(installer)
    installables_by_name = {installable.name: installable for installable in installables}
    for installable in installables:
        installable.link(installables_by_name)
    installables = sorted(filter(lambda installable: filter_aggregate(args.filter, installable, args.filter_match_all),
                                 installables), key=lambda x: x.sort_key)
    destination: Path
    if args.command == 'list':
        print("Installation candidates:")
        for installable in installables:
            print(installable.name)
            _LOGGER.debug(installable)
        sys.exit(0)
    elif args.command == 'verify':
        num_ok = 0
        num_not_ok = 0
        for installable in installables:
            print(f"Checking {installable.name}")
            if not installable.is_installed():
                _LOGGER.info("%s is not installed", installable.name)
                num_not_ok += 1
            elif not installable.verify():
                _LOGGER.info("%s is not OK", installable.name)
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
        _LOGGER.debug('Starting Amazon Check')
        languages = ['c', 'c++', 'd', 'cuda']

        for language in languages:
            _LOGGER.info('Checking %s libraries', language)
            [_, libraries] = get_properties_compilers_and_libraries(language, _LOGGER)

            for libraryid in libraries:
                _LOGGER.debug('Checking %s', libraryid)
                for version in libraries[libraryid]['versionprops']:
                    includepaths = libraries[libraryid]['versionprops'][version]['path']
                    for includepath in includepaths:
                        _LOGGER.debug('Checking for library %s %s: %s', libraryid, version, includepath)
                        if not os.path.exists(includepath):
                            _LOGGER.error('Path missing for library %s %s: %s', libraryid, version, includepath)
                        else:
                            _LOGGER.debug('Found path for library %s %s: %s', libraryid, version, includepath)

                    libpaths = libraries[libraryid]['versionprops'][version]['libpath']
                    for libpath in libpaths:
                        _LOGGER.debug('Checking for library %s %s: %s', libraryid, version, libpath)
                        if not os.path.exists(libpath):
                            _LOGGER.error('Path missing for library %s %s: %s', libraryid, version, libpath)
                        else:
                            _LOGGER.debug('Found path for library %s %s: %s', libraryid, version, libpath)
    elif args.command == 'squash':
        for installable in installables:
            if not installable.is_installed():
                _LOGGER.warning("%s wasn't installed; skipping squash", installable.name)
                continue
            destination = args.image_dir / f"{installable.install_path}.img"
            if destination.exists() and not args.force:
                _LOGGER.info("Skipping %s as it already exists at %s", installable.name, destination)
                continue
            if installable.nightly_like:
                _LOGGER.info("Skipping %s as it looks like a nightly", installable.name)
                continue
            _LOGGER.info("Squashing %s to %s", installable.name, destination)
            installable.squash_to(destination)
    elif args.command == 'squashcheck':
        if not Path(args.image_dir).exists():
            _LOGGER.error("Missing squash directory %s", args.image_dir)
            exit(1)

        for installable in installables:
            destination = Path(args.image_dir / f"{installable.install_path}.img")
            if installable.nightly_like:
                if destination.exists():
                    _LOGGER.error("Found squash: %s for nightly", installable.name)
            elif not destination.exists():
                _LOGGER.error("Missing squash: %s (for %s)", installable.name, destination)

        squash_mount_check(args.image_dir, '', context)

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
                            _LOGGER.error("%s installed OK, but doesn't appear as installed after", installable.name)
                            failed.append(installable.name)
                        else:
                            _LOGGER.info("%s installed OK", installable.name)
                            num_installed += 1
                    else:
                        _LOGGER.info("%s failed to install", installable.name)
                        failed.append(installable.name)
                except Exception as e:  # pylint: disable=broad-except
                    _LOGGER.info("%s failed to install: %s\n%s", installable.name, e, traceback.format_exc(5))
                    failed.append(installable.name)
            else:
                _LOGGER.info("%s is already installed, skipping", installable.name)
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
                    _LOGGER.info("%s is not installed, unable to build", installable.name)
                    num_skipped += 1
                else:
                    try:
                        [num_installed, num_skipped, num_failed] = installable.build(args.buildfor)
                        if num_installed > 0:
                            _LOGGER.info("%s built OK", installable.name)
                        elif num_failed:
                            _LOGGER.info("%s failed to build", installable.name)
                    except RuntimeError as e:
                        if args.buildfor:
                            raise e
                        else:
                            _LOGGER.info("%s failed to build: %s", installable.name, e)
                            num_failed += 1
            else:
                _LOGGER.info("%s is already built, skipping", installable.name)
                num_skipped += 1
        print(f'{num_installed} packages built OK, {num_skipped} skipped, and {num_failed} failed build')
        if num_failed:
            sys.exit(1)
        sys.exit(0)
    elif args.command == 'reformat':
        libyaml = LibraryYaml(args.yaml_dir)
        libyaml.reformat()
    elif args.command == 'addtoprustcrates':
        libyaml = LibraryYaml(args.yaml_dir)
        libyaml.add_top_rust_crates()
        libyaml.save()
    elif args.command == 'generaterustprops':
        propfile = Path(os.path.join(os.curdir, 'props'))
        with propfile.open(mode="w", encoding="utf-8") as file:
            libyaml = LibraryYaml(args.yaml_dir)
            props = libyaml.get_ce_properties_for_rust_libraries()
            file.write(props)
    elif args.command == 'addcrate':
        libyaml = LibraryYaml(args.yaml_dir)
        libyaml.add_rust_crate(args.filter[0], args.filter[1])
        libyaml.save()

    else:
        raise RuntimeError("Er, whoops")


if __name__ == '__main__':
    main()
