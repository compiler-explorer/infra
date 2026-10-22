from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner
from lib.cli.links import links_scrub_ips
from lib.links_ip_scrub import PlannedUpdate, ScanReport


def _report(unscrubbable: int = 0) -> ScanReport:
    report = ScanReport(scanned=2)
    report.updates.append(PlannedUpdate("abcdef", "abcdefgh", old="192.0.2.33, 198.51.100.7", new="192.0.2.0"))
    if unscrubbable:
        report.unscrubbable["unparseable"] = unscrubbable
    return report


@pytest.fixture(name="scrub")
def fixture_scrub():
    with (
        patch("lib.cli.links.fetch_ip_ranges", return_value={"prefixes": [], "ipv6_prefixes": []}),
        patch("lib.cli.links.scan_links") as scan_links,
        patch("lib.cli.links.point_in_time_recovery") as pitr,
        patch("lib.cli.links.are_you_sure") as are_you_sure,
        patch("lib.cli.links.apply_updates") as apply_updates,
    ):
        steps = MagicMock()
        steps.attach_mock(are_you_sure, "are_you_sure")
        steps.attach_mock(apply_updates, "apply_updates")
        scan_links.return_value = _report()
        pitr.return_value = {"PointInTimeRecoveryStatus": "ENABLED", "LatestRestorableDateTime": "then"}
        yield {"scan_links": scan_links, "pitr": pitr, "apply_updates": apply_updates, "steps": steps}


def test_dry_run_by_default_writes_nothing(scrub):
    result = CliRunner().invoke(links_scrub_ips, [])

    assert result.exit_code == 0
    assert "DRY RUN: would rewrite 1 records" in result.output
    scrub["apply_updates"].assert_not_called()
    scrub["pitr"].assert_not_called()
    assert "192.0.2" not in result.output
    assert "198.51.100" not in result.output


def test_apply_confirms_before_writing(scrub):
    result = CliRunner().invoke(links_scrub_ips, ["--apply"])

    assert result.exit_code == 0
    assert [name for name, _, _ in scrub["steps"].mock_calls] == ["are_you_sure", "apply_updates"]
    assert "192.0.2" not in result.output
    assert "198.51.100" not in result.output


def test_apply_refuses_without_point_in_time_recovery(scrub):
    scrub["pitr"].return_value = {"PointInTimeRecoveryStatus": "DISABLED"}

    result = CliRunner().invoke(links_scrub_ips, ["--apply"])

    assert result.exit_code != 0
    assert "Point-in-time recovery is not enabled" in result.output
    scrub["apply_updates"].assert_not_called()


def test_apply_refuses_while_records_are_unscrubbable(scrub):
    scrub["scan_links"].return_value = _report(unscrubbable=1)

    result = CliRunner().invoke(links_scrub_ips, ["--apply"])

    assert result.exit_code != 0
    assert "refusing to write" in result.output
    scrub["apply_updates"].assert_not_called()
    scrub["pitr"].assert_not_called()


def _fail_after_one_write(_updates, _rate, outcomes):
    outcomes["updated"] += 1
    raise RuntimeError("boom")


def test_apply_reports_progress_when_a_write_fails(scrub):
    scrub["apply_updates"].side_effect = _fail_after_one_write

    result = CliRunner().invoke(links_scrub_ips, ["--apply"])

    assert isinstance(result.exception, RuntimeError)
    assert "1  updated" in result.output
