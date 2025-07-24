import pytest
from lib.cli.runner import runner_check_discovery_json_contents


def test_should_find_remote_compilers():
    runner_check_discovery_json_contents("/gpu/api /winprod/api", "")


def test_should_error_on_missing_remote_compilers():
    with pytest.raises(RuntimeError, match="does not contain gpu"):
        runner_check_discovery_json_contents("/winprod/api", "")


def test_should_not_error_on_missing_remote_compilers_if_skipped():
    runner_check_discovery_json_contents("/winprod/api", "gpu")
    runner_check_discovery_json_contents("", "gpu,winprod")
