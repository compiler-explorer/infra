from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory, mkdtemp

from lib.cefs.config import CefsConfig


import logging

_LOGGER = logging.getLogger(__name__)


class SquashFsCreator:
    def __init__(self, config: CefsConfig):
        self._config = config
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
        return self._config.image_root / f"{self._sha}.sqfs"

    @property
    def cefs_path(self) -> Path:
        assert self._sha is not None
        return self._config.mountpoint / self._sha

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
