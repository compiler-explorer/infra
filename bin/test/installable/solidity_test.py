from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from lib.installable.solidity import SolidityInstallable, solidity_available_releases
from lib.installation_context import InstallationContext


@pytest.fixture(name="fake_context")
def fake_context_fixture():
    solidity_available_releases.cache_clear()
    context = MagicMock(spec=InstallationContext)
    context.fetcher = MagicMock()
    context.fetcher.get.return_value.json.return_value = {
        "releases": {"0.8.30": "solc-linux-amd64-v0.8.30+commit.73712a01"}
    }
    yield context
    solidity_available_releases.cache_clear()


def _config(name: str) -> dict[str, Any]:
    return {
        "context": ["compilers", "solidity"],
        "name": name,
        "dir": f"solc-{name}",
        "url": "https://binaries.soliditylang.org/linux-amd64",
        "filename": "solc",
    }


def test_solidity_installable_resolves_release_url(fake_context):
    installable = SolidityInstallable(fake_context, _config("0.8.30"))
    assert installable.url == "https://binaries.soliditylang.org/linux-amd64/solc-linux-amd64-v0.8.30+commit.73712a01"
    assert installable.install_path == "solc-0.8.30"
    fake_context.fetcher.get.assert_called_once_with("https://binaries.soliditylang.org/linux-amd64/list.json")


def test_solidity_installable_unknown_version_raises(fake_context):
    with pytest.raises(RuntimeError, match="Unable to find solidity 9.9.9"):
        SolidityInstallable(fake_context, _config("9.9.9"))
