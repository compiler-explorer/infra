import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import List

import click

from lib.amazon import get_tools_releases, download_release_file
from lib.ce_utils import display_releases, are_you_sure
from lib.cli import cli
from lib.releases import Hash, Version, VersionSource

CE_TOOLS_LOCATION = '/opt/compiler-explorer/demanglers/'


@cli.group()
def tools():
    """Tool installation commands."""


@tools.command(name='list')
@click.option('--destination', type=click.Path(file_okay=False, dir_okay=True),
              default=CE_TOOLS_LOCATION)
@click.option('-b', '--branch', type=str, help='show only BRANCH (may be specified more than once)',
              metavar='BRANCH', multiple=True)
def tools_list(destination: str, branch: List[str]):
    current_version = Hash('')
    hash_file = Path(destination) / 'git_hash'
    if hash_file.exists():
        current_version = Hash(hash_file.read_text(encoding='utf-8').strip())
    display_releases(current_version, set(branch), get_tools_releases())


@tools.command(name='install')
@click.option('--destination', type=click.Path(file_okay=False, dir_okay=True),
              default=CE_TOOLS_LOCATION)
@click.argument('version')
def tools_install(version: str, destination: str):
    """
    Install demangling tools version VERSION.
    """
    releases = get_tools_releases()
    version = Version.from_string(version, assumed_source=VersionSource.GITHUB)
    for release in releases:
        if release.version == version:
            if not are_you_sure("deploy tools"):
                return
            with TemporaryDirectory(prefix='ce-tools-') as td_str:
                td = Path(td_str)
                tar_dest = td / 'tarball.tar.xz'
                unpack_dest = td / 'tools'
                unpack_dest.mkdir()
                download_release_file(release.key, str(tar_dest))
                subprocess.check_call([
                    'tar',
                    '--strip-components', '1',
                    '-C', str(unpack_dest),
                    '-Jxf', str(tar_dest)
                ])
                subprocess.check_call([
                    'rsync',
                    '-a',
                    '--delete-after',
                    f'{unpack_dest}/',
                    f'{destination}/'
                ])
            click.echo(f'Tools updated to {version}')
            return
    click.echo(f'Unable to find version {version}')
