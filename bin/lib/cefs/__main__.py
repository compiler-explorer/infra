from __future__ import annotations

import datetime
import getpass
import logging
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import click

from lib.cefs.config import CefsConfig
from lib.cefs.root import CefsFsRoot
from lib.cefs.root_image import CefsRootImage
from lib.cefs.squash import SquashFsCreator

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class CliContext:
    config: CefsConfig


@click.group()
@click.option(
    "--cefs-mountpoint",
    default=Path("/cefs"),
    metavar="MOUNTPOINT",
    type=click.Path(file_okay=False, path_type=Path),
    help="Install or assume cefs is to use MOUNTPOINT",
    show_default=True,
)
@click.option(
    "--squash-image-root",
    default=Path("/opt/cefs-images"),
    metavar="IMAGE_DIR",
    type=click.Path(file_okay=False, path_type=Path),
    help="Store or look for squashfs images in IMAGE_DIR",
    show_default=True,
)
@click.option("--debug/--no-debug", help="Turn on debugging")
@click.option("--log-to-console", is_flag=True, help="Log output to console, even if logging to a file is requested")
@click.option("--log", metavar="LOGFILE", help="Log to LOGFILE", type=click.Path(dir_okay=False, writable=True))
@click.pass_context
def cli(
    ctx: click.Context,
    cefs_mountpoint: Path,
    squash_image_root: Path,
    debug: bool,
    log_to_console: bool,
    log: Optional[str],
):
    """Administrate the Compiler Explorer File System (cefs)."""
    formatter = logging.Formatter(fmt="%(asctime)s %(name)-15s %(levelname)-8s %(message)s")
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG if debug else logging.INFO)
    if log:
        file_handler = logging.FileHandler(log)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    if not log or log_to_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)
    ctx.obj = CliContext(config=CefsConfig(mountpoint=cefs_mountpoint, image_root=squash_image_root))


@cli.command
@click.pass_obj
def install(context: CliContext):
    """Install the CEFS mountpoint and associated directories. Needs to be run as root."""
    config = context.config
    if os.geteuid() != 0:
        click.echo("Installing cefs needs root privileges.")
        sys.exit(1)
    if not Path("/etc/auto.master.d").is_dir():
        click.echo("Installing cefs needs autofs. Please install manually using e.g. `apt install autofs`")
        sys.exit(1)
    click.echo("Writing config files...")
    auto_cefs_config_file = Path("/etc/auto.cefs")
    auto_cefs_config_file.write_text(
        f"* -fstype=squashfs,loop,nosuid,nodev,ro :{config.image_root}/&.sqfs\n", encoding="utf-8"
    )
    Path("/etc/auto.master.d/cefs.autofs").write_text(
        f"{config.mountpoint} {auto_cefs_config_file}  --negative-timeout 1", encoding="utf-8"
    )
    if not config.image_root.is_dir():
        click.echo(
            f"Creating {config.image_root} squash image root.\n"
            f"By default this will be writable BY ALL USERS, but is sticky like /tmp. This is to make it usable\n"
            f"by unprivileged users. You are responsible for making sure that's ok, and changing the directory\n"
            f"permissions as appropriate."
        )
        config.image_root.mkdir(parents=True)
        config.image_root.chmod(0o1777)
    click.echo("Restarting autofs")
    subprocess.check_call(["service", "autofs", "restart"])
    click.echo(f"CEFS installed with a root at {config.mountpoint} and squash image root at {config.image_root}.")
    click.echo(
        f"Note that the root {config.mountpoint} will appear empty, "
        f"but will automatically mount on demand when required."
    )


@cli.command
@click.pass_obj
def create_image(context: CliContext):
    """Create an empty image."""
    created_path = _create_empty(context.config)
    click.echo(f"Fresh new cefs image created at {created_path}")


def _create_empty(config: CefsConfig) -> Path:
    creator = SquashFsCreator(config)
    with creator.creation_path() as path:
        image = CefsRootImage(cefs_mountpoint=config.mountpoint)
        image.add_metadata(f"Initial empty image created at {datetime.datetime.utcnow()} by {getpass.getuser()}")
        image.render_to(path)
    return creator.cefs_path


@cli.command
@click.argument("root", type=click.Path(file_okay=False, dir_okay=False, writable=True, path_type=Path), required=True)
@click.pass_obj
def create_root(context: CliContext, root: Path):
    """Create an empty cefs root at ROOT."""
    empty_path = _create_empty(context.config)
    CefsFsRoot.create(base_image=empty_path, fs_root=root, config=context.config)


@cli.command
@click.argument("root", type=click.Path(file_okay=False, dir_okay=True, path_type=Path), required=True)
@click.pass_obj
def import_image(context: CliContext, root: Path):
    """Import an existing filesystem ROOT."""
    # DOESNT work on cefs images as they contain symlinks and...that would be bad for consolidation
    # todo check it isn't?
    # todo maybe support exclusions? `-ef` one line per file
    creator = SquashFsCreator(context.config)
    creator.import_existing_path(root)
    click.echo(f"Imported new cefs image created at {creator.cefs_path}")


# TODO how to start the whole thing off? make an empty root and manually symlink it in position?
# TODO cases where we have a GIANT image that only exists because one dir is in it
#  ie repacking and refreshing old images
# TODO consolidation in general! aim is to have very few layers, after all.
# TODO delete old things
# TODO keep track of a symlink and its history /opt/compiler-explorer --> /opt/compiler-explorer.history?
# TODO better naming of dirs/manifest for each so we know who and why created each layer?
# TODO should we separate out root squashfs images from data?
# TODO detect cefs roots in `install` and redirect to buildroot?
# TODO delete/etc
# TODO handle old symlinks of trunk (and do trunk etc!)
# TODO should "cefs_mountpoint" be onfigurable.
# TODO should there be a magic file? should metadata.txt by .metadata.txt or indeed just that special file?
# TODO should probably check on mksquashfs cmdline flags like block size, my laptop used 131072 block size but I swear
#  another machine used 4k
# TODO can add metadata directly with `--pseudofile` magic:
#  https://github.com/plougher/squashfs-tools/blob/a5df5dc42c564d10c1aebf2063fc30c26850ddc3/USAGE#L261
# TODO installation from ce_install of nightly things won't work as they try to remove things, and we need a solution
#  for that


def main():
    cli(prog_name="cefs")  # pylint: disable=unexpected-keyword-arg,no-value-for-parameter


if __name__ == "__main__":
    main()
