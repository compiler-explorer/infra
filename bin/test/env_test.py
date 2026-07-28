"""Tests for environment properties."""

import pytest

from lib.env import Environment


@pytest.mark.parametrize(
    "env",
    [Environment.PROD, Environment.STAGING, Environment.BETA, Environment.GPU, Environment.AARCH64PROD],
)
def test_discovery_is_required_for_serving_environments(env):
    assert env.discovery_required


@pytest.mark.parametrize("env", [Environment.WINPROD, Environment.WINSTAGING])
def test_discovery_is_required_for_windows_environments_it_is_produced_for(env):
    assert env.discovery_required


def test_discovery_is_not_required_for_wintest():
    """Nothing produces a discovery for wintest, which serves its own compiler set."""
    assert not Environment.WINTEST.discovery_required


@pytest.mark.parametrize("env", [Environment.RUNNER, Environment.GPU_RUNNER, Environment.WINRUNNER])
def test_discovery_is_not_required_for_runners(env):
    assert not env.discovery_required
    assert env.is_runner


def test_winrunner_is_windows_so_it_looks_for_zip_builds():
    assert Environment.WINRUNNER.is_windows
    assert Environment.WINRUNNER.version_key == "version/winrunner"


def test_winrunner_does_not_keep_builds():
    assert not Environment.WINRUNNER.keep_builds
