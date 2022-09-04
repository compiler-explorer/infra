import logging
from pathlib import Path

_LOGGER = logging.getLogger(__name__)


class StagingDir:
    def __init__(self, staging_dir: Path, keep_afterwards: bool):
        self._dir = staging_dir
        self._keep_afterwards = keep_afterwards
        _LOGGER.debug("Creating staging dir %s", self._dir)
        self._dir.mkdir(parents=True)

    @property
    def path(self) -> Path:
        return self._dir
