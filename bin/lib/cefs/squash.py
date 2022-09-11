from __future__ import annotations

import contextlib
import logging
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Optional, Iterable, Iterator

from lib.cefs.config import CefsConfig

_LOGGER = logging.getLogger(__name__)


class SquashFsCreator:
    def __init__(self, config: CefsConfig):
        self._config = config
        self._sha: Optional[str] = None

    def import_existing_path(self, path: Path):
        assert self._sha is None
        with TemporaryDirectory(prefix="ce-squash-builder") as tmp_dir:
            tmp_sqfs = Path(tmp_dir) / "temp.sqfs"
            subprocess.check_call(
                [
                    "mksquashfs",
                    str(path),
                    str(tmp_sqfs),
                    "-all-root",
                    "-root-mode",
                    "755",
                    "-progress",
                    "-comp",
                    "zstd",
                ]
            )
            self._sha, _filename = subprocess.check_output(["shasum", str(tmp_sqfs)]).decode("utf-8").split()
            if not self.image.exists():
                _LOGGER.info("New squashfs image: %s", self.image)
                tmp_sqfs.replace(self.image)
            else:
                _LOGGER.info("Existing: %s", self.image)
                tmp_sqfs.unlink()

    @property
    def image(self) -> Path:
        assert self._sha is not None
        return self._config.image_root / f"{self._sha}.sqfs"

    @property
    def cefs_path(self) -> Path:
        assert self._sha is not None
        return self._config.mountpoint / self._sha

    @contextlib.contextmanager
    def creation_path(self) -> Iterator[Path]:
        with TemporaryDirectory(prefix="ce-install-temp") as temp_dir:
            tmp_path = Path(temp_dir)
            yield tmp_path
            self.import_existing_path(tmp_path)
