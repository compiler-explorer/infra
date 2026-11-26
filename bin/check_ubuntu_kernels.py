#!/usr/bin/env python3
"""List Ubuntu 24.04 AWS kernel updates worth opening an issue for.

Reports AWS kernels published to noble-updates in the last few days, plus released noble kernel
fixes for any CVE passed with --cve. Prints one JSON object per line with an issue title and body.

Usage:
    ./bin/check_ubuntu_kernels.py [--days DAYS] [--cve CVE-ID ...]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "lib"))

from lib.ubuntu_kernels import CveFix, KernelRelease, fetch_recent_releases, fetch_released_fixes


def release_body(release: KernelRelease) -> str:
    published = release.published.strftime("%Y-%m-%d %H:%M UTC")
    return f"`{release.source}` {release.version} was published to noble-updates on {published}.\n\n{release.url}"


def fix_body(fix: CveFix) -> str:
    return f"Ubuntu marks {fix.cve} as released for `{fix.package}` {fix.version} on noble.\n\n{fix.url}"


def main() -> int:
    parser = argparse.ArgumentParser(description="List recent Ubuntu 24.04 kernel updates")
    parser.add_argument("--days", type=int, default=7, help="How far back to look (default: 7)")
    parser.add_argument("--cve", action="append", default=[], help="CVE to watch for a released fix (repeatable)")
    args = parser.parse_args()

    for release in fetch_recent_releases(args.days):
        body = release_body(release)
        print(json.dumps({"title": release.issue_title, "body": body}))
    for cve in args.cve:
        for fix in fetch_released_fixes(cve):
            body = fix_body(fix)
            print(json.dumps({"title": fix.issue_title, "body": body}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
