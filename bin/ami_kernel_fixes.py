#!/usr/bin/env python3
"""Print "Fixes #N" lines for open kernel update issues when a PR diff changes a Linux AMI.

Usage:
    ./bin/ami_kernel_fixes.py PR_DIFF ISSUES_JSON

ISSUES_JSON is the output of `gh issue list --json number,title`.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "lib"))

from lib.ubuntu_kernels import changes_linux_ami, kernel_issue_numbers


def main() -> int:
    parser = argparse.ArgumentParser(description="List kernel issues fixed by an AMI change")
    parser.add_argument("diff", type=Path, help="Unified diff of the PR")
    parser.add_argument("issues", type=Path, help="Open issues as JSON")
    args = parser.parse_args()

    if not changes_linux_ami(args.diff.read_text()):
        return 0
    for number in kernel_issue_numbers(json.loads(args.issues.read_text())):
        print(f"Fixes #{number}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
