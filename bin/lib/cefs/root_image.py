from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Dict, List, Mapping

_LOGGER = logging.getLogger(__name__)
METADATA_FILENAME = "metadata.txt"


class BadCefsImage(RuntimeError):
    pass


class BadCefsLink(RuntimeError):
    pass


class CefsRootImage:
    """
    Holds information about a CEFS root image, which is a directory full of symlinks to other CEFS images, and some
    metadata. TODO naming
    """

    def __init__(self, *, cefs_mountpoint: Path, directory: Optional[Path] = None):
        self._cefs_mountpoint = cefs_mountpoint.resolve(strict=True)
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
                if not link.is_relative_to(self._cefs_mountpoint):
                    raise BadCefsImage(f"Found a symlink that wasn't a symlink to cefs: {entry} links to {link}")
                _LOGGER.debug("Found existing %s -> %s", relative, link)
                self._catalog[relative] = link
            elif entry.is_dir():
                self._recurse_find_paths(entry, root_path)
            elif entry.is_file():
                if relative == Path(METADATA_FILENAME):
                    self._metadata = entry.read_text(encoding="utf-8").splitlines(keepends=False)
                else:
                    raise BadCefsImage(f"Found an unexpected file: {entry}")
            else:
                raise BadCefsImage(f"Found an unexpected entry: {entry}")

    def add_metadata(self, metadata: str) -> None:
        self._metadata.append(metadata)

    def link_path(self, subdir: Path, cefs_link: Path):
        if not cefs_link.is_relative_to(self._cefs_mountpoint):
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
