from pathlib import Path
from typing import Dict, Any

from lib.installable.installable import Installable
from lib.installation_context import InstallationContext
from lib.staging import StagingDir

import logging

_LOGGER = logging.getLogger(__name__)

class GoInstallable(Installable):
    def __init__(self, install_context: InstallationContext, config: Dict[str, Any]):
        super().__init__(install_context, config)
        _LOGGER.error("Not implemented")

    def do_go_install(self, staging: StagingDir, component: str, install_to: Path) -> None:
        _LOGGER.error("Not implemented")

    def maybe_set_rpath(self, maybe_elf_file: Path, rpath: str) -> None:
        _LOGGER.error("Not implemented")

    def stage(self, staging: StagingDir) -> None:
        _LOGGER.error("Not implemented")

    def should_install(self) -> bool:
        _LOGGER.error("Not implemented")
        return super().should_install()

    def verify(self) -> bool:
        if not super().verify():
            return False
        _LOGGER.error("Not implemented")
        return True

    def install(self) -> None:
        super().install()
        _LOGGER.error("Not implemented")

    def __repr__(self) -> str:
        return f"GoInstallable({self.name}, {self.install_path})"
