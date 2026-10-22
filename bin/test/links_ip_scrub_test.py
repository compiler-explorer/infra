from collections import Counter
from unittest.mock import patch

import pytest
from botocore.exceptions import ClientError
from lib.links_ip_scrub import (
    AddressClassifier,
    PlannedUpdate,
    ScanReport,
    anonymize_ip,
    apply_updates,
    assess,
    format_report,
    looks_anonymised,
    mask,
    scan_links,
    scan_segment,
)

# Documentation ranges only (RFC 5737, RFC 3849). 198.51.100.0/24 and 2001:db8:cf::/48 stand in for
# CloudFront, 203.0.113.0/25 for the rest of AWS; 192.0.2.0/24 and 203.0.113.128/25 are ordinary clients.
FAKE_RANGES = {
    "prefixes": [
        {"ip_prefix": "198.51.100.0/24", "service": "CLOUDFRONT"},
        {"ip_prefix": "198.51.100.0/24", "service": "AMAZON"},
        {"ip_prefix": "203.0.113.0/25", "service": "AMAZON"},
    ],
    "ipv6_prefixes": [{"ipv6_prefix": "2001:db8:cf::/48", "service": "CLOUDFRONT"}],
}
EDGE = "198.51.100.7"
CLIENT = "192.0.2.33"
OTHER_CLIENT = "203.0.113.200"
AWS_PROXY = "203.0.113.9"
CLIENT_V6 = "2001:db8:1234:5678:9abc:def0:1234:5678"


@pytest.fixture(name="classifier")
def fixture_classifier() -> AddressClassifier:
    return AddressClassifier(FAKE_RANGES)


@pytest.mark.parametrize(
    "ip, expected",
    [
        ("192.0.2.33", "192.0.2.0"),
        ("192.0.2.0", "192.0.2.0"),
        ("2001:db8:1:2:3:4:5:6", "2001:db8:1:2:3:0:0:0"),
        ("2001:db8:abcd:123::1", "2001:db8:abcd:0:0:0"),
        ("2001:db8:abcd:0:0:0", "2001:db8:abcd:0:0:0"),
        ("localhost", "localhost"),
    ],
)
def test_anonymize_ip_matches_compiler_explorer(ip, expected):
    assert anonymize_ip(ip) == expected


@pytest.mark.parametrize(
    "ip, expected",
    [
        ("::ffff:192.0.2.1", "::ffff:192.0.2.0"),
        ("::FFFF:192.0.2.1", "::FFFF:192.0.2.0"),
    ],
)
def test_anonymize_ip_applies_the_ipv4_rule_to_a_dotted_tail(ip, expected):
    """CE's anonymizeIp returns these unchanged."""
    assert anonymize_ip(ip) == expected


@pytest.mark.parametrize(
    "value",
    ["192.0.2.0", "::ffff:192.0.2.0", "2001:db8:abcd:123:0:0:0", "2001:db8:1:2:3:0:0:0", "0.0.0.0", "::1"],
)
def test_looks_anonymised(value):
    assert looks_anonymised(value)


@pytest.mark.parametrize(
    "value",
    [
        "192.0.2.33",
        "2001:db8::1",
        "::ffff:192.0.2.1",
        "",
        "192.0.2.0, 198.51.100.7",
        "192.0.2.0\n",
        "Unknown",
        "2001:db8:1:2:3:4:5:6:0:0:0",
        "\u0661\u0662.0.2.0",
    ],
)
def test_does_not_look_anonymised(value):
    assert not looks_anonymised(value)


@pytest.mark.parametrize(
    "entry, kind",
    [
        ("192.0.2.0", "anonymised"),
        ("2001:db8:abcd:123:0:0:0", "anonymised"),
        (EDGE, "cloudfront"),
        ("2001:db8:cf::1", "cloudfront"),
        ("198.51.100.0", "cloudfront"),
        ("10.1.2.3", "private"),
        ("fd00::1", "private"),
        (AWS_PROXY, "aws"),
        (CLIENT, "public-raw"),
        (OTHER_CLIENT, "public-raw"),
        (CLIENT_V6, "public-raw"),
        ("0.0.0.0", "sentinel"),
        ("migrated-from-local", "sentinel"),
        ("::1", "sentinel"),
        ("::ffff:192.0.2.0", "anonymised"),
        ("::ffff:192.0.2.1", "public-raw"),
        ("::ffff:10.0.0.5", "private"),
        ("::ffff:127.0.0.1", "private"),
        ("::ffff:198.51.100.7", "cloudfront"),
        ("::ffff:203.0.113.9", "aws"),
        ("not an address", "unparseable"),
    ],
)
def test_classifier_kind(classifier, entry, kind):
    assert classifier.kind(entry) == kind


@pytest.mark.parametrize(
    "creation_ip, shape",
    [
        (f"192.0.2.0, {EDGE}", "anonymised|cloudfront"),
        (f"2001:db8:abcd:123:0:0:0, {EDGE}", "anonymised|cloudfront"),
        ("192.0.2.0", "anonymised"),
        ("2001:db8:abcd:123:0:0:0", "anonymised"),
        (f"192.0.2.0, 192.0.2.0, {EDGE}", "anonymised|anonymised|cloudfront"),
        (f"{EDGE}, {EDGE}", "cloudfront|cloudfront"),
        ("0.0.0.0", "sentinel"),
        ("migrated-from-local", "sentinel"),
        ("::1", "sentinel"),
    ],
)
def test_clean_records_are_left_alone(classifier, creation_ip, shape):
    assessment = assess(creation_ip, classifier)

    assert assessment.shape == shape
    assert not assessment.needs_scrub
    assert not assessment.unscrubbable


@pytest.mark.parametrize(
    "creation_ip, shape, replacement",
    [
        (f"10.0.0.0, {CLIENT}, {EDGE}", "anonymised|public-raw|cloudfront", "192.0.2.0"),
        (f"10.1.2.3, {CLIENT}, {EDGE}", "private|public-raw|cloudfront", "192.0.2.0"),
        (f"{CLIENT}, {EDGE}", "public-raw|cloudfront", "192.0.2.0"),
        (CLIENT, "public-raw", "192.0.2.0"),
        (f"10.0.0.0, {AWS_PROXY}, {EDGE}", "anonymised|aws|cloudfront", "203.0.113.0"),
        (f"10.1.2.3, {EDGE}", "private|cloudfront", "10.1.2.0"),
        ("10.1.2.3", "private", "10.1.2.0"),
        (f"10.0.0.0, {OTHER_CLIENT}, {CLIENT}, {EDGE}", "anonymised|public-raw|public-raw|cloudfront", "192.0.2.0"),
        (
            f"2001:db8:abcd:123:0:0:0, {CLIENT}, {EDGE}",
            "anonymised|public-raw|cloudfront",
            "192.0.2.0",
        ),
        (f"10.0.0.0, {CLIENT_V6}, {EDGE}", "anonymised|public-raw|cloudfront", "2001:db8:1234:5678:9abc:0:0:0"),
        (f"10.0.0.0,{CLIENT},{EDGE}", "anonymised|public-raw|cloudfront", "192.0.2.0"),
        ("::ffff:192.0.2.1", "public-raw", "::ffff:192.0.2.0"),
        (f"10.0.0.0, {CLIENT}", "anonymised|public-raw", "192.0.2.0"),
        (f"{CLIENT}, unknown, {EDGE}", "public-raw|sentinel|cloudfront", "192.0.2.0"),
    ],
)
def test_leaking_records_get_the_anonymised_client(classifier, creation_ip, shape, replacement):
    assessment = assess(creation_ip, classifier)

    assert assessment.shape == shape
    assert assessment.replacement == replacement


@pytest.mark.parametrize(
    "creation_ip",
    [
        "not an address",
        f"{CLIENT}:5678, {EDGE}",
        f"10.0.0.0, {CLIENT}:5678, {EDGE}",
        f"10.0.0.0, Unknown, {EDGE}",
        f"{CLIENT}, {EDGE},",
        f"{CLIENT},,{EDGE}",
        f"{CLIENT};{EDGE}",
        "[2001:db8::1]",
        "64:ff9b::192.0.2.33",
    ],
)
def test_value_with_no_usable_client_is_reported_not_rewritten(classifier, creation_ip):
    assessment = assess(creation_ip, classifier)

    assert assessment.unscrubbable
    assert not assessment.needs_scrub


def test_empty_value_is_reported_not_rewritten(classifier):
    assert assess("", classifier).unscrubbable


def test_mask_hides_every_nonzero_group():
    assert mask(f"10.0.0.0, {CLIENT}, {EDGE}") == "n.0.0.0, n.0.n.n, n.n.n.n"
    assert mask("2001:db8:abcd:0:0:0") == "n:n:n:0:0:0"
    assert mask("0.0.0.0") == "0.0.0.0"


def test_planned_update_repr_hides_addresses():
    update = PlannedUpdate(prefix="abcdef", unique_subhash="abcdefgh", old=f"{CLIENT}, {EDGE}", new="192.0.2.0")

    assert "192.0.2" not in repr(update)


def _item(creation_ip: str | None, date: str = "2023-04-01T00:00:00") -> dict:
    item = {"prefix": {"S": "abcdef"}, "unique_subhash": {"S": "abcdefgh"}, "creation_date": {"S": date}}
    if creation_ip is not None:
        item["creation_ip"] = {"S": creation_ip}
    return item


def _report(classifier, *items) -> ScanReport:
    report = ScanReport()
    for item in items:
        report.add(item, classifier)
    return report


def test_report_plans_updates_only_for_leaks(classifier):
    report = _report(
        classifier,
        _item(f"10.0.0.0, {CLIENT}, {EDGE}", "2019-01-01T00:00:00"),
        _item(f"192.0.2.0, {EDGE}"),
        _item(None),
        _item("not an address"),
    )

    assert report.scanned == 4
    assert report.without_ip == 1
    assert report.scrubs_by_year == {"2019": 1}
    assert report.unscrubbable == {"unparseable": 1}
    assert len(report.updates) == 1
    assert report.updates[0].old == f"10.0.0.0, {CLIENT}, {EDGE}"
    assert report.updates[0].new == "192.0.2.0"


def test_report_flags_a_creation_ip_that_is_not_a_string(classifier):
    item = _item(None)
    item["creation_ip"] = {"L": [{"S": CLIENT}]}

    report = _report(classifier, item)

    assert report.without_ip == 0
    assert report.unscrubbable == {"not a string": 1}
    assert not report.updates


def test_format_report_never_prints_an_address(classifier):
    leaks = [f"10.0.0.0, {CLIENT}, {EDGE}", f"{OTHER_CLIENT}, {EDGE}", f"10.0.0.0, {CLIENT_V6}, {EDGE}"]
    report = _report(classifier, *(_item(leak) for leak in leaks), _item("::ffff:192.0.2.1"), _item("192.0.2.1 junk"))

    output = "\n".join(format_report(report))

    for address in (CLIENT, OTHER_CLIENT, CLIENT_V6, EDGE, "192.0.2", "203.0.113", "2001:db8"):
        assert address not in output
    assert "anonymised|public-raw|cloudfront -> n.0.n.0" in output
    assert "anonymised|public-raw|cloudfront  <- scrub" in output
    assert "unparseable  <- UNSCRUBBABLE" in output


def test_format_report_splits_a_shape_that_is_only_partly_unscrubbable(classifier):
    report = _report(classifier, _item(f"{CLIENT}, {EDGE}"), _item(f"2001:db8:1:2:3:4:5::, {EDGE}"))

    assert "  <- scrub, 1 UNSCRUBBABLE" in "\n".join(format_report(report))


@patch("lib.links_ip_scrub.dynamodb_client")
def test_scan_segment_reads_every_page(mock_client, classifier):
    mock_client.get_paginator.return_value.paginate.return_value = [
        {"Items": [_item(f"10.0.0.0, {CLIENT}, {EDGE}")]},
        {"Items": [_item(f"192.0.2.0, {EDGE}")]},
    ]

    report = scan_segment(classifier, 3, 16)

    assert report.scanned == 2
    assert len(report.updates) == 1
    kwargs = mock_client.get_paginator.return_value.paginate.call_args.kwargs
    assert kwargs["TableName"] == "links"
    assert (kwargs["Segment"], kwargs["TotalSegments"]) == (3, 16)


@patch("lib.links_ip_scrub.dynamodb_client")
def test_scan_links_merges_every_segment(mock_client, classifier):
    mock_client.get_paginator.return_value.paginate.return_value = [
        {"Items": [_item(f"10.0.0.0, {CLIENT}, {EDGE}"), _item(f"192.0.2.0, {EDGE}")]}
    ]

    report = scan_links(classifier, 4)

    assert report.scanned == 8
    assert len(report.updates) == 4
    segments = sorted(call.kwargs["Segment"] for call in mock_client.get_paginator.return_value.paginate.call_args_list)
    assert segments == [0, 1, 2, 3]


def _conditional_failure() -> ClientError:
    return ClientError({"Error": {"Code": "ConditionalCheckFailedException", "Message": "nope"}}, "UpdateItem")


@patch("lib.links_ip_scrub.time.sleep")
@patch("lib.links_ip_scrub.dynamodb_client")
def test_apply_updates_writes_conditionally(mock_client, _mock_sleep):
    update = PlannedUpdate(prefix="abcdef", unique_subhash="abcdefgh", old=f"{CLIENT}, {EDGE}", new="192.0.2.0")

    outcomes: Counter[str] = Counter()
    apply_updates([update], 100, outcomes)

    assert outcomes == {"updated": 1}
    mock_client.update_item.assert_called_once_with(
        TableName="links",
        Key={"prefix": {"S": "abcdef"}, "unique_subhash": {"S": "abcdefgh"}},
        UpdateExpression="SET #ip = :new",
        ConditionExpression="#ip = :old",
        ExpressionAttributeNames={"#ip": "creation_ip"},
        ExpressionAttributeValues={":new": {"S": "192.0.2.0"}, ":old": {"S": f"{CLIENT}, {EDGE}"}},
    )


@patch("lib.links_ip_scrub.time.sleep")
@patch("lib.links_ip_scrub.dynamodb_client")
def test_apply_updates_skips_records_changed_since_the_scan(mock_client, _mock_sleep):
    mock_client.update_item.side_effect = [_conditional_failure(), {}]
    updates = [PlannedUpdate("abcdef", f"abcdef{n}", old=CLIENT, new="192.0.2.0") for n in range(2)]

    outcomes: Counter[str] = Counter()
    apply_updates(updates, 100, outcomes)

    assert outcomes == {"changed since scan, skipped": 1, "updated": 1}


@patch("lib.links_ip_scrub.time.sleep")
@patch("lib.links_ip_scrub.dynamodb_client")
def test_apply_updates_stops_on_unexpected_errors(mock_client, _mock_sleep):
    mock_client.update_item.side_effect = [
        {},
        ClientError(
            {"Error": {"Code": "ProvisionedThroughputExceededException", "Message": "slow down"}}, "UpdateItem"
        ),
    ]
    updates = [PlannedUpdate("abcdef", f"abcdef{n}", old=CLIENT, new="192.0.2.0") for n in range(3)]
    outcomes: Counter[str] = Counter()

    with pytest.raises(ClientError):
        apply_updates(updates, 100, outcomes)

    assert mock_client.update_item.call_count == 2
    assert outcomes == {"updated": 1}


@patch("lib.links_ip_scrub.time.sleep")
@patch("lib.links_ip_scrub.time.monotonic")
@patch("lib.links_ip_scrub.dynamodb_client")
def test_apply_updates_paces_writes(_mock_client, mock_monotonic, mock_sleep):
    mock_monotonic.return_value = 1000.0
    updates = [PlannedUpdate("abcdef", f"abcdef{n}", old=CLIENT, new="192.0.2.0") for n in range(3)]

    apply_updates(updates, 4, Counter())

    assert [call.args[0] for call in mock_sleep.call_args_list] == [0.25, 0.5]
