"""Tests for the Windows runner CLI helpers."""

import json

import pytest
from lib.cli.win_runner import MIN_EXPECTED_COMPILERS, check_discovery_json_contents


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
