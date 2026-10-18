"""Remove unanonymised client addresses from ``creation_ip`` in the ``links`` table.

From 2018 until compiler-explorer#9126, creating a short link stored the raw X-Forwarded-For header,
anonymising only its leftmost entry. A client behind a proxy that adds its own X-Forwarded-For had its
real public address stored verbatim in a later entry. Affected records are rewritten to the single
anonymised client address that records written since the fix hold.

Nothing here may print or log a raw address: reports use address kinds and masked patterns only.
"""

import bisect
import ipaddress
import re
import time
from collections import Counter
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Self

import requests
from botocore.exceptions import ClientError

from lib.amazon import LINKS_TABLE, dynamodb_client

IP_RANGES_URL = "https://ip-ranges.amazonaws.com/ip-ranges.json"

# Values that identify no user. `ce link name` writes 0.0.0.0, and anonymizeIp passes "localhost" through.
SENTINELS = frozenset({"0.0.0.0", "::1", "unknown", "localhost", "migrated-from-local"})

SENTINEL = "sentinel"
ANONYMISED = "anonymised"
CLOUDFRONT = "cloudfront"
PRIVATE = "private"
AWS = "aws"
PUBLIC_RAW = "public-raw"
UNPARSEABLE = "unparseable"
NOT_A_STRING = "not a string"

# A CloudFront edge address belongs to AWS, not to a user. Any other AWS address may be someone's own proxy.
SAFE_KINDS = frozenset({SENTINEL, ANONYMISED, CLOUDFRONT})
# Kinds that can stand for the client. A sentinel or an edge never does.
_CLIENT_KINDS = frozenset({ANONYMISED, PRIVATE, AWS, PUBLIC_RAW})

_ANONYMISED_IPV4_RE = re.compile(r"(?:::ffff:)?\d{1,3}\.\d{1,3}\.\d{1,3}\.0", re.IGNORECASE | re.ASCII)
# anonymizeIp swaps the last three groups for ":0:0:0" textually, so a "::"-compressed address comes out
# with fewer than eight groups and is not valid IPv6. It is anonymised all the same.
# anonymizeIp keeps at most five groups in front of ":0:0:0"; anything longer has a raw address inside it.
_ANONYMISED_IPV6_RE = re.compile(r"(?:[0-9A-Fa-f]{0,4}:){1,5}0:0:0")
_ANONYMIZE_IPV4_RE = re.compile(r"\.\d{1,3}\Z", re.ASCII)
_ANONYMIZE_IPV6_RE = re.compile(r"(?::[0-9A-Fa-f]{0,4}){3}\Z")
_MASK_GROUP_RE = re.compile(r"[0-9A-Fa-f]+")

# Python's is_private also covers the documentation and reserved ranges; these are the ones a proxy
# plausibly puts in X-Forwarded-For.
_PRIVATE_NETWORKS = tuple(
    ipaddress.ip_network(network)
    for network in (
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "100.64.0.0/10",
        "127.0.0.0/8",
        "169.254.0.0/16",
        "::1/128",
        "fc00::/7",
        "fe80::/10",
    )
)

IpNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network
IpAddress = ipaddress.IPv4Address | ipaddress.IPv6Address


def anonymize_ip(ip: str) -> str:
    """Port of anonymizeIp from compiler-explorer's lib/utils.ts, so scrubbed records match new ones.

    One deliberate difference: any address with a dotted IPv4 tail, such as ::ffff:192.0.2.1, gets the IPv4
    rule. CE's version sends anything containing ":" down the IPv6 path, whose pattern cannot match a dotted
    tail, and returns it whole.
    """
    if "localhost" in ip:
        return ip
    if _ANONYMIZE_IPV4_RE.search(ip):
        return _ANONYMIZE_IPV4_RE.sub(".0", ip)
    if ":" in ip:
        return _ANONYMIZE_IPV6_RE.sub(":0:0:0", ip)
    return ip


def looks_anonymised(value: str) -> bool:
    return value in SENTINELS or bool(_ANONYMISED_IPV4_RE.fullmatch(value) or _ANONYMISED_IPV6_RE.fullmatch(value))


def _mask_group(match: re.Match[str]) -> str:
    return "0" if match.group() == "0" else "n"


def mask(value: str) -> str:
    """Reduce a creation_ip value to a pattern safe to print, e.g. "n.n.n.0, n.n.n.n"."""
    if value in SENTINELS:
        return value
    return _MASK_GROUP_RE.sub(_mask_group, value)


class _Ranges:
    """Merged address intervals per IP version, so membership is a bisect, not a walk over thousands of prefixes."""

    def __init__(self, networks: Iterable[IpNetwork]):
        merged: dict[int, list[tuple[int, int]]] = {4: [], 6: []}
        for network in sorted(networks, key=lambda n: (n.version, int(n.network_address))):
            low, high = int(network.network_address), int(network.broadcast_address)
            intervals = merged[network.version]
            if intervals and low <= intervals[-1][1] + 1:
                intervals[-1] = (intervals[-1][0], max(intervals[-1][1], high))
            else:
                intervals.append((low, high))
        self._starts = {version: [low for low, _ in intervals] for version, intervals in merged.items()}
        self._ends = {version: [high for _, high in intervals] for version, intervals in merged.items()}

    def __contains__(self, address: IpAddress) -> bool:
        index = bisect.bisect_right(self._starts[address.version], int(address)) - 1
        return index >= 0 and int(address) <= self._ends[address.version][index]


def _service_networks(ip_ranges: dict[str, Any], service: str) -> list[IpNetwork]:
    networks: list[IpNetwork] = [
        ipaddress.ip_network(prefix["ip_prefix"]) for prefix in ip_ranges["prefixes"] if prefix["service"] == service
    ]
    networks += [
        ipaddress.ip_network(prefix["ipv6_prefix"])
        for prefix in ip_ranges["ipv6_prefixes"]
        if prefix["service"] == service
    ]
    return networks


def fetch_ip_ranges() -> dict[str, Any]:
    response = requests.get(IP_RANGES_URL, timeout=30)
    response.raise_for_status()
    return response.json()


class AddressClassifier:
    """Sorts each X-Forwarded-For entry into a kind, using AWS's published ip-ranges.json.

    The ranges are today's, so an edge CloudFront has since retired reads as public-raw and gets scrubbed.
    That errs in the safe direction.
    """

    def __init__(self, ip_ranges: dict[str, Any]):
        self._cloudfront = _Ranges(_service_networks(ip_ranges, "CLOUDFRONT"))
        self._aws = _Ranges(_service_networks(ip_ranges, "AMAZON"))

    def kind(self, entry: str) -> str:
        if entry in SENTINELS:
            return SENTINEL
        try:
            address = ipaddress.ip_address(entry)
        except ValueError:
            return ANONYMISED if looks_anonymised(entry) else UNPARSEABLE
        if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
            address = address.ipv4_mapped
        if address in self._cloudfront:
            return CLOUDFRONT
        if looks_anonymised(entry):
            return ANONYMISED
        if any(address in network for network in _PRIVATE_NETWORKS):
            return PRIVATE
        if address in self._aws:
            return AWS
        return PUBLIC_RAW


@dataclass(frozen=True)
class Assessment:
    shape: str
    replacement: str | None = field(default=None, repr=False)
    unscrubbable: bool = False

    @property
    def needs_scrub(self) -> bool:
        return self.replacement is not None


def assess(creation_ip: str, classifier: AddressClassifier) -> Assessment:
    entries = [entry.strip() for entry in creation_ip.split(",")]
    kinds = [classifier.kind(entry) for entry in entries]
    shape = "|".join(kinds)
    if all(kind in SAFE_KINDS for kind in kinds):
        return Assessment(shape)
    # An entry we cannot parse may be the real client in a form we don't recognise (a port, brackets), so
    # picking another entry could silently record the wrong address.
    if UNPARSEABLE in kinds:
        return Assessment(shape, unscrubbable=True)
    # Behind CloudFront and the ALB the header ends with the edge's address, so the rightmost entry before it
    # is the client as CE has recorded it since the fix (trust proxy=2). Entries further left are dropped.
    candidates = [entry for entry, kind in zip(entries, kinds, strict=True) if kind in _CLIENT_KINDS]
    if not candidates:
        return Assessment(shape, unscrubbable=True)
    replacement = anonymize_ip(candidates[-1])
    if not looks_anonymised(replacement):
        return Assessment(shape, unscrubbable=True)
    return Assessment(shape, replacement)


@dataclass(frozen=True)
class PlannedUpdate:
    prefix: str
    unique_subhash: str
    old: str = field(repr=False)
    new: str = field(repr=False)


@dataclass
class ScanReport:
    scanned: int = 0
    without_ip: int = 0
    shapes: Counter[str] = field(default_factory=Counter)
    scrubs: Counter[tuple[str, str]] = field(default_factory=Counter)
    scrubs_by_year: Counter[str] = field(default_factory=Counter)
    unscrubbable: Counter[str] = field(default_factory=Counter)
    updates: list[PlannedUpdate] = field(default_factory=list, repr=False)

    def add(self, item: dict[str, Any], classifier: AddressClassifier) -> None:
        self.scanned += 1
        attribute = item.get("creation_ip")
        if attribute is None:
            self.without_ip += 1
            return
        creation_ip = attribute.get("S")
        if creation_ip is None:
            self.shapes[NOT_A_STRING] += 1
            self.unscrubbable[NOT_A_STRING] += 1
            return
        assessment = assess(creation_ip, classifier)
        self.shapes[assessment.shape] += 1
        if assessment.unscrubbable:
            self.unscrubbable[assessment.shape] += 1
        if assessment.replacement is None:
            return
        self.scrubs[(assessment.shape, mask(assessment.replacement))] += 1
        self.scrubs_by_year[item.get("creation_date", {}).get("S", "")[:4] or "no date"] += 1
        self.updates.append(
            PlannedUpdate(
                prefix=item["prefix"]["S"],
                unique_subhash=item["unique_subhash"]["S"],
                old=creation_ip,
                new=assessment.replacement,
            )
        )

    def merge(self, other: Self) -> None:
        self.scanned += other.scanned
        self.without_ip += other.without_ip
        self.shapes.update(other.shapes)
        self.scrubs.update(other.scrubs)
        self.scrubs_by_year.update(other.scrubs_by_year)
        self.unscrubbable.update(other.unscrubbable)
        self.updates.extend(other.updates)


def scan_segment(classifier: AddressClassifier, segment: int, total_segments: int) -> ScanReport:
    report = ScanReport()
    paginator = dynamodb_client.get_paginator("scan")
    pages = paginator.paginate(
        TableName=LINKS_TABLE,
        Segment=segment,
        TotalSegments=total_segments,
        ProjectionExpression="#p, #u, #ip, #d",
        ExpressionAttributeNames={
            "#p": "prefix",
            "#u": "unique_subhash",
            "#ip": "creation_ip",
            "#d": "creation_date",
        },
    )
    for page in pages:
        for item in page["Items"]:
            report.add(item, classifier)
    return report


def scan_links(classifier: AddressClassifier, total_segments: int) -> ScanReport:
    report = ScanReport()
    with ThreadPoolExecutor(total_segments) as pool:
        futures = [pool.submit(scan_segment, classifier, segment, total_segments) for segment in range(total_segments)]
        for future in futures:
            report.merge(future.result())
    return report


def format_report(report: ScanReport) -> list[str]:
    lines = [f"Scanned {report.scanned:,} records, {report.without_ip:,} without a creation_ip", "", "All shapes:"]
    for shape, count in report.shapes.most_common():
        unscrubbable = report.unscrubbable[shape]
        if unscrubbable == count:
            marker = "  <- UNSCRUBBABLE"
        elif unscrubbable:
            marker = f"  <- scrub, {unscrubbable:,} UNSCRUBBABLE"
        elif all(kind in SAFE_KINDS for kind in shape.split("|")):
            marker = ""
        else:
            marker = "  <- scrub"
        lines.append(f"  {count:>10,}  {shape}{marker}")
    to_rewrite = len(report.updates)
    lines += ["", f"To rewrite: {to_rewrite:,} records, as shape -> new value pattern:"]
    for (shape, pattern), count in report.scrubs.most_common():
        lines.append(f"  {count:>10,}  {shape} -> {pattern}")
    lines += ["", "To rewrite, by creation year:"]
    for year, count in sorted(report.scrubs_by_year.items()):
        lines.append(f"  {count:>10,}  {year}")
    if report.unscrubbable:
        lines += ["", "UNSCRUBBABLE: no entry could be anonymised. --apply refuses to run while any remain:"]
        for shape, count in report.unscrubbable.most_common():
            lines.append(f"  {count:>10,}  {shape}")
    return lines


def point_in_time_recovery() -> dict[str, Any]:
    response = dynamodb_client.describe_continuous_backups(TableName=LINKS_TABLE)
    return response["ContinuousBackupsDescription"]["PointInTimeRecoveryDescription"]


def apply_updates(updates: list[PlannedUpdate], writes_per_second: float, outcomes: Counter[str]) -> None:
    """Rewrite each record, but only if creation_ip still holds what the scan saw. Safe to re-run.

    Outcomes are counted into the caller's counter, so they survive an error part way through.
    """
    total = len(updates)
    interval = 1.0 / writes_per_second
    next_write = time.monotonic()
    for done, update in enumerate(updates, start=1):
        delay = next_write - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        next_write = max(next_write, time.monotonic()) + interval
        try:
            dynamodb_client.update_item(
                TableName=LINKS_TABLE,
                Key={"prefix": {"S": update.prefix}, "unique_subhash": {"S": update.unique_subhash}},
                UpdateExpression="SET #ip = :new",
                ConditionExpression="#ip = :old",
                ExpressionAttributeNames={"#ip": "creation_ip"},
                ExpressionAttributeValues={":new": {"S": update.new}, ":old": {"S": update.old}},
            )
            outcomes["updated"] += 1
        except ClientError as error:
            if error.response["Error"]["Code"] != "ConditionalCheckFailedException":
                raise
            outcomes["changed since scan, skipped"] += 1
        if done % 1000 == 0:
            print(f"  {done:,} / {total:,}")
