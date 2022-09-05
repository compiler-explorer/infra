import logging
import os
import shutil
import sys
import subprocess
from pathlib import Path
from tempfile import mkdtemp, NamedTemporaryFile, TemporaryDirectory
from typing import Optional, Mapping, List, Dict
from dataclasses import dataclass

import click

_LOGGER = logging.getLogger(__name__)
METADATA_FILENAME = "metadata.txt"


@dataclass(frozen=True)
class CliContext:
    cefs_root: Path
    squash_image_root: Path


@click.group()
@click.option(
    "--cefs-root",
    default=Path("/cefs"),
    metavar="CEFS_ROOT",
    type=click.Path(file_okay=False, path_type=Path),
    help="Install or assume cefs is installed at CEFS_ROOT",
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
    cefs_root: Path,
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
    ctx.obj = CliContext(cefs_root=cefs_root, squash_image_root=squash_image_root)


@cli.command
@click.pass_obj
def install(context: CliContext):
    """Install the CEFS. Needs to be run as root."""
    if os.geteuid() != 0:
        click.echo("Installing cefs needs root privileges.")
        sys.exit(1)
    if not Path("/etc/auto.master.d").is_dir():
        click.echo("Installing cefs needs autofs. Please install manually using e.g. `apt install autofs`")
        sys.exit(1)
    click.echo("Writing config files...")
    auto_cefs_config_file = Path("/etc/auto.cefs")
    auto_cefs_config_file.write_text(
        f"* -fstype=squashfs,loop,nosuid,nodev,ro :{context.squash_image_root}/&.sqfs\n", encoding="utf-8"
    )
    Path("/etc/auto.master.d/cefs.autofs").write_text(
        f"{context.cefs_root} {auto_cefs_config_file}  --negative-timeout 1", encoding="utf-8"
    )
    if not context.squash_image_root.is_dir():
        click.echo(
            f"Creating {context.squash_image_root} squash image root.\n"
            f"By default this will be writable BY ALL USERS, but is sticky like /tmp. This is to make it usable\n"
            f"by unprivileged users. You are responsible for making sure that's ok, and changing the directory\n"
            f"permissions as appropriate."
        )
        context.squash_image_root.mkdir(parents=True)
        context.squash_image_root.chmod(0o1777)
    click.echo("Restarting autofs")
    subprocess.check_call(["service", "autofs", "restart"])
    click.echo(
        f"CEFS installed with a root at {context.cefs_root} and squash image root at {context.squash_image_root}."
    )
    click.echo(
        f"Note that the root {context.cefs_root} will appear empty, "
        f"but will automatically mount on demand when required."
    )


class SquashFsCreator:
    def __init__(self, *, squash_image_root: Path, cefs_root: Path):
        self._squash_image_root = squash_image_root
        self._cefs_root = cefs_root
        self._sha = None

    def _close(self):
        with TemporaryDirectory(prefix="ce-squash-builder") as tmp_dir:
            tmp_sqfs = Path(tmp_dir) / "temp.sqfs"
            subprocess.check_call(
                [
                    "/usr/bin/mksquashfs",
                    str(self._path),
                    str(tmp_sqfs),
                    "-all-root",
                    "-root-mode",
                    "755",
                    "-progress",
                    "-comp",
                    "zstd",
                ]
            )
            self._sha, _filename = subprocess.check_output(["/usr/bin/shasum", str(tmp_sqfs)]).decode("utf-8").split()
            if not self.image.exists():
                _LOGGER.info("New squashfs image: %s", self.image)
                tmp_sqfs.replace(self.image)
            else:
                _LOGGER.info("Existing: %s", self.image)
                tmp_sqfs.unlink()

    @property
    def image(self) -> Path:
        assert self._sha is not None
        return self._squash_image_root / f"{self._sha}.sqfs"

    @property
    def cefs_path(self) -> Path:
        assert self._sha is not None
        return self._cefs_root / self._sha

    def __enter__(self):
        self._path = Path(mkdtemp(prefix="ce-install-temp"))
        return self._path

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if not exc_type:
                self._close()
        finally:
            subprocess.check_call(["chmod", "-R", "u+w", str(self._path)])
            shutil.rmtree(self._path, ignore_errors=True)


class BadCefsRoot(RuntimeError):
    pass


class BadCefsLink(RuntimeError):
    pass


class CefsImage:
    """
    Holds information about a CEFS root image, which is a directory full of symlinks to
    other CEFS images, and some metadata.
    """

    def __init__(self, *, cefs_root: Path, directory: Optional[Path] = None):
        self._cefs_root = cefs_root.resolve(strict=True)
        self._catalog: Dict[Path, Path] = {}
        self._metadata: List[str] = []

        if directory:
            self._recurse_find_paths(directory, directory)
            _LOGGER.info("CEFS image at %s has %d entries", directory, len(self.catalog))

    def _recurse_find_paths(self, path: Path, root_path: Path):
        for entry in path.iterdir():
            relative = entry.relative_to(root_path)
            if entry.is_symlink():
                link = entry.readlink()
                if not link.is_relative_to(self._cefs_root):
                    raise BadCefsRoot(f"Found a symlink that wasn't a symlink to cefs: {entry} links to {link}")
                _LOGGER.debug("Found existing %s -> %s", relative, link)
                self._catalog[relative] = link
            elif entry.is_dir():
                self._recurse_find_paths(entry, root_path)
            elif entry.is_file():
                if relative == Path(METADATA_FILENAME):
                    self._metadata = entry.read_text(encoding="utf-8").splitlines(keepends=False)
                else:
                    raise BadCefsRoot(f"Found an unexpected file: {entry}")
            else:
                raise BadCefsRoot(f"Found an unexpected entry: {entry}")

    def add_metadata(self, metadata: str) -> None:
        self._metadata.append(metadata)

    def link_path(self, subdir: Path, cefs_link: Path):
        if not cefs_link.is_relative_to(self._cefs_root):
            raise BadCefsLink(f"Link is not relative to cefs: {cefs_link}")
        self._catalog[subdir] = cefs_link

    @property
    def catalog(self) -> Mapping[Path, Path]:
        return self._catalog

    @property
    def metadata(self) -> List[str]:
        return self._metadata

    def render_to(self, destination: Path) -> None:
        destination.mkdir(parents=True, exist_ok=True)
        (destination / METADATA_FILENAME).write_text("\n".join(self._metadata) + "\n", encoding="utf-8")
        for entry, dest in self.catalog.items():
            source_dir = destination / entry
            source_dir.parent.mkdir(parents=True, exist_ok=True)
            source_dir.symlink_to(dest)


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


def main():
    cli(prog_name="cefs")  # pylint: disable=unexpected-keyword-arg,no-value-for-parameter


if __name__ == "__main__":
    main()
