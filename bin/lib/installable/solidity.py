from __future__ import annotations

import functools
from typing import Dict, Any

from lib.installable.installable import SingleFileInstallable
from lib.installation_context import InstallationContext


@functools.lru_cache(maxsize=1)
def solidity_available_releases(context: InstallationContext, list_url: str):
    response = context.fetcher.get(list_url)
    return response.json()["releases"]


class SolidityInstallable(SingleFileInstallable):
    def __init__(self, install_context: InstallationContext, config: Dict[str, Any]):
        super().__init__(install_context, config)
        self.install_path = self.config_get("dir")
        artifacts = solidity_available_releases(self.install_context, self.url + "/list.json")
        release_path = artifacts[self.target_name]
        if self.target_name not in artifacts:
            raise RuntimeError(f"Unable to find solidity {self.target_name}")
        self.url = f"{self.url}/{release_path}"
        self.filename = self.config_get("filename")
        self._setup_check_exe(self.install_path)

    def __repr__(self) -> str:
        return f"SolidityInstallable({self.name}, {self.install_path})"
