"""Track the Ubuntu 24.04 AWS kernels our EC2 AMIs run."""

from __future__ import annotations

import json
import re
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

LAUNCHPAD_ARCHIVE = "https://api.launchpad.net/1.0/ubuntu/+archive/primary"
SERIES = "noble"
POCKET = "Updates"

TRACKED_SOURCE = re.compile(r"^linux-meta-aws-\d+\.\d+$")


@dataclass(frozen=True)
class KernelRelease:
    source: str
    version: str
    published: datetime

    @property
    def flavour(self) -> str:
        return self.source.removeprefix("linux-meta-")

    @property
    def issue_title(self) -> str:
        return f"Ubuntu 24.04 kernel update: {self.flavour} {self.version}"

    @property
    def url(self) -> str:
        return f"https://launchpad.net/ubuntu/+source/{self.source}/{self.version}"


def published_sources_url() -> str:
    return (
        f"{LAUNCHPAD_ARCHIVE}?ws.op=getPublishedSources&source_name=linux-meta"
        f"&distro_series=https://api.launchpad.net/1.0/ubuntu/{SERIES}"
        f"&pocket={POCKET}&status=Published&ws.size=300"
    )


def parse_entries(entries: list[dict[str, Any]]) -> list[KernelRelease]:
    releases = []
    for entry in entries:
        source = entry["source_package_name"]
        if not TRACKED_SOURCE.match(source) or not entry.get("date_published"):
            continue
        published = datetime.fromisoformat(entry["date_published"])
        releases.append(KernelRelease(source=source, version=entry["source_package_version"], published=published))
    return sorted(releases, key=lambda r: r.published)


def recent_releases(releases: list[KernelRelease], now: datetime, days: int) -> list[KernelRelease]:
    cutoff = now - timedelta(days=days)
    return [r for r in releases if r.published >= cutoff]


def fetch_entries(url: str) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    next_url: str | None = url
    while next_url:
        with urllib.request.urlopen(next_url, timeout=60) as response:
            page = json.load(response)
        entries.extend(page["entries"])
        next_url = page.get("next_collection_link")
    return entries


def fetch_recent_releases(days: int) -> list[KernelRelease]:
    entries = fetch_entries(published_sources_url())
    now = datetime.now(UTC)
    return recent_releases(parse_entries(entries), now, days)


CVE_URL = "https://ubuntu.com/security/cves/{cve}.json"
TRACKED_PACKAGE = re.compile(r"^linux-aws-\d+\.\d+$")


@dataclass(frozen=True)
class CveFix:
    cve: str
    package: str
    version: str

    @property
    def issue_title(self) -> str:
        return f"{self.cve} fixed in Ubuntu 24.04: {self.package} {self.version}"

    @property
    def url(self) -> str:
        return f"https://ubuntu.com/security/{self.cve}"


def released_fixes(cve: str, data: dict[str, Any]) -> list[CveFix]:
    fixes = []
    for package in data.get("packages", []):
        if not TRACKED_PACKAGE.match(package["name"]):
            continue
        for status in package["statuses"]:
            if status["release_codename"] == SERIES and status["status"] == "released":
                fixes.append(CveFix(cve=cve, package=package["name"], version=status["description"]))
    return fixes


def fetch_released_fixes(cve: str) -> list[CveFix]:
    url = CVE_URL.format(cve=cve)
    with urllib.request.urlopen(url, timeout=60) as response:
        data = json.load(response)
    return released_fixes(cve, data)


KERNEL_ISSUE_TITLE = re.compile(r"^(Ubuntu 24\.04 kernel update: |CVE-\S+ fixed in Ubuntu 24\.04: )")
AMI_ID = re.compile(r"\bami-[0-9a-f]{8,}\b")


def changes_linux_ami(diff: str) -> bool:
    in_terraform = False
    for line in diff.splitlines():
        if line.startswith("+++ "):
            in_terraform = line.startswith("+++ b/terraform/") and line.endswith(".tf")
            continue
        if not in_terraform or not line.startswith("+"):
            continue
        code = line[1:].strip()
        if code.startswith(("#", "//")) or "win" in code.lower():
            continue
        if AMI_ID.search(code):
            return True
    return False


def kernel_issue_numbers(issues: list[dict[str, Any]]) -> list[int]:
    return sorted(issue["number"] for issue in issues if KERNEL_ISSUE_TITLE.match(issue["title"]))
