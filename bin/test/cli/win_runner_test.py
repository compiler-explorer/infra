"""Tests for the Windows runner CLI helpers."""

import json

import pytest
from lib.builds_core import print_missing_version_hint
from lib.cli.win_runner import (
    MIN_EXPECTED_COMPILERS,
    STARTUP_FAILED,
    STARTUP_READY,
    STARTUP_WAITING,
    check_discovery_json_contents,
    startup_state,
)
from lib.env import Config, Environment

RUNNING_SERVICE = "Status   Name      DisplayName\nRunning  cestartup cestartup"
STOPPED_SERVICE = "Status   Name      DisplayName\nStopped  cestartup cestartup"


def make_compilers(count: int) -> str:
    return json.dumps([{"id": f"compiler-{i}", "exe": f"Z:/compilers/c{i}/bin/cc.exe"} for i in range(count)])


def test_check_discovery_json_accepts_a_full_discovery():
    check_discovery_json_contents(make_compilers(MIN_EXPECTED_COMPILERS))


def test_check_discovery_json_rejects_invalid_json():
    with pytest.raises(RuntimeError, match="not valid json"):
        check_discovery_json_contents("{definitely not json")


def test_check_discovery_json_rejects_non_list():
    with pytest.raises(RuntimeError, match="expected a list"):
        check_discovery_json_contents('{"id": "gcc"}')


def test_check_discovery_json_rejects_too_few_compilers():
    with pytest.raises(RuntimeError, match="expected at least"):
        check_discovery_json_contents(make_compilers(MIN_EXPECTED_COMPILERS - 1))


def test_check_discovery_json_rejects_compilers_without_an_exe():
    compilers = json.loads(make_compilers(MIN_EXPECTED_COMPILERS))
    compilers[0]["exe"] = ""
    with pytest.raises(RuntimeError, match="no exe"):
        check_discovery_json_contents(json.dumps(compilers))


def test_check_discovery_json_reports_the_count(capsys):
    check_discovery_json_contents(make_compilers(MIN_EXPECTED_COMPILERS + 7))
    assert f"{MIN_EXPECTED_COMPILERS + 7} compilers" in capsys.readouterr().out


def test_startup_state_ready_when_the_file_is_there():
    assert startup_state("True\n", RUNNING_SERVICE) == STARTUP_READY


def test_startup_state_waits_while_the_service_runs():
    assert startup_state("False\n", RUNNING_SERVICE) == STARTUP_WAITING


def test_startup_state_waits_when_the_instance_is_not_answering_yet():
    assert startup_state("", "") == STARTUP_WAITING


def test_startup_state_fails_once_the_service_has_stopped():
    assert startup_state("False\n", STOPPED_SERVICE) == STARTUP_FAILED


def test_startup_state_prefers_ready_over_a_stopped_service():
    """The service stops as soon as start.ps1 returns, so both can be true at once."""
    assert startup_state("True\n", STOPPED_SERVICE) == STARTUP_READY


def test_missing_version_hint_is_printed_for_windows(capsys):
    print_missing_version_hint(Config(env=Environment.WINPROD))
    assert "deploy-win" in capsys.readouterr().out


def test_missing_version_hint_is_silent_for_linux():
    print_missing_version_hint(Config(env=Environment.STAGING))
