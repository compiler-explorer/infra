from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from lib.ubuntu_kernels import (
    CveFix,
    KernelRelease,
    changes_linux_ami,
    kernel_issue_numbers,
    parse_entries,
    recent_releases,
    released_fixes,
)


def entry(name: str, version: str, published: str | None) -> dict[str, str | None]:
    return {"source_package_name": name, "source_package_version": version, "date_published": published}


def test_parse_entries_keeps_aws_hwe_only():
    entries = [
        entry("linux-meta", "6.8.0-147.147", "2026-10-12T21:41:55.541612+00:00"),
        entry("linux-meta-aws", "6.8.0-1067.70", "2026-10-12T21:41:55+00:00"),
        entry("linux-meta-hwe-7.0", "7.0.0-42.42~24.04.1", "2026-10-28T00:08:20+00:00"),
        entry("linux-meta-aws-6.17", "6.17.0-1020.20~24.04.1+1", "2026-07-23T16:30:00+00:00"),
        entry("linux-meta-aws-7.0", "7.0.0-1018.19~24.04.1", "2026-11-19T12:26:00+00:00"),
        entry("linux-meta-gcp", "6.8.0-1050.53", "2026-10-12T21:41:55+00:00"),
        entry("linux-meta-azure-6.17", "6.17.0-1010.10", "2026-10-12T21:41:55+00:00"),
        entry("linux-meta-lowlatency", "6.8.0-147.147", "2026-10-12T21:41:55+00:00"),
    ]
    sources = [r.source for r in parse_entries(entries)]
    assert sources == ["linux-meta-aws-6.17", "linux-meta-aws-7.0"]


def test_parse_entries_skips_unpublished():
    assert parse_entries([entry("linux-meta-aws-7.0", "7.0.0-1019.20~24.04.1", None)]) == []


def test_recent_releases_filters_by_age():
    now = datetime(2026, 11, 1, tzinfo=UTC)
    old = KernelRelease("linux-meta-aws", "6.8.0-1067.70", datetime(2026, 10, 12, tzinfo=UTC))
    new = KernelRelease("linux-meta-aws-7.0", "7.0.0-1014.14~24.04.1", datetime(2026, 10, 28, tzinfo=UTC))
    assert recent_releases([old, new], now, days=7) == [new]


def test_issue_title_names_flavour():
    published = datetime(2026, 10, 28, tzinfo=UTC)
    assert KernelRelease("linux-meta-aws-7.0", "7.0.0-1014.14~24.04.1", published).issue_title == (
        "Ubuntu 24.04 kernel update: aws-7.0 7.0.0-1014.14~24.04.1"
    )


def test_url_points_at_launchpad_source():
    release = KernelRelease("linux-meta-aws", "6.8.0-1067.70", datetime(2026, 10, 12, tzinfo=UTC))
    assert release.url == "https://launchpad.net/ubuntu/+source/linux-meta-aws/6.8.0-1067.70"


def cve_package(name: str, codename: str, status: str, description: str = "") -> dict[str, Any]:
    return {"name": name, "statuses": [{"release_codename": codename, "status": status, "description": description}]}


def test_released_fixes_reports_released_noble_kernels_only():
    data = {
        "packages": [
            cve_package("linux-aws", "noble", "released", "6.8.0-1069.74"),
            cve_package("linux-aws-7.0", "noble", "released", "7.0.0-1018.19~24.04.1"),
            cve_package("linux", "noble", "released", "6.8.0-149.149"),
            cve_package("linux-hwe-7.0", "noble", "released", "7.0.0-43.43~24.04.1"),
            cve_package("linux-aws-7.0", "jammy", "released", "7.0.0-1017.18"),
            cve_package("linux-gcp", "noble", "released", "6.8.0-1073.81"),
        ]
    }
    assert released_fixes("CVE-2026-98432", data) == [
        CveFix("CVE-2026-98432", "linux-aws-7.0", "7.0.0-1018.19~24.04.1")
    ]


def test_released_fixes_none_while_pending():
    data = {"packages": [cve_package("linux-aws-7.0", "noble", "pending", "7.0.0-1018.19~24.04.1")]}
    assert released_fixes("CVE-2026-98432", data) == []


def test_cve_fix_issue_title():
    fix = CveFix("CVE-2026-98432", "linux-aws", "6.8.0-1069.74")
    assert fix.issue_title == "CVE-2026-98432 fixed in Ubuntu 24.04: linux-aws 6.8.0-1069.74"


def tf_diff(path: str, removed: str, added: str) -> str:
    return f"""diff --git a/{path} b/{path}
--- a/{path}
+++ b/{path}
@@ -1,3 +1,3 @@
 locals {{
-{removed}
+{added}
"""


def test_changes_linux_ami_detects_prod_image_bump():
    diff = tf_diff(
        "terraform/lc.tf",
        '  prod_image_id = "ami-0ac50ab7a0b2ac4b2"',
        '  prod_image_id = "ami-0123456789abcdef0"',
    )
    assert changes_linux_ami(diff)


def test_changes_linux_ami_ignores_windows_images():
    diff = tf_diff(
        "terraform/lc.tf",
        '  winprod_image_id = "ami-0b0826bc65a0426b3"',
        '  winprod_image_id = "ami-0123456789abcdef0"',
    )
    assert not changes_linux_ami(diff)


def test_changes_linux_ami_ignores_comments_and_non_terraform():
    assert not changes_linux_ami(tf_diff("terraform/ec2.tf", "", '//  ami = "ami-0b97d4bbd77733fc0"'))
    assert not changes_linux_ami(tf_diff("docs/amis.md", "", "Use ami-0123456789abcdef0"))


def test_changes_linux_ami_ignores_removed_lines():
    assert not changes_linux_ami(tf_diff("terraform/lc.tf", '  prod_image_id = "ami-0ac50ab7a0b2ac4b2"', ""))


def test_kernel_issue_numbers_matches_watch_titles_only():
    issues = [
        {"number": 2581, "title": "Ubuntu 24.04 kernel update: aws-7.0 7.0.0-1018.19~24.04.1"},
        {"number": 2590, "title": "CVE-2026-98432 fixed in Ubuntu 24.04: linux-aws-7.0 7.0.0-1018.19~24.04.1"},
        {"number": 2500, "title": "Upgrade to Ubuntu 24.04 on builders"},
    ]
    assert kernel_issue_numbers(issues) == [2581, 2590]
