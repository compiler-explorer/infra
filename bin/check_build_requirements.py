#!/usr/bin/env python3
"""Check if PR additions require building compilers or tools.

Usage:
    ./bin/check_build_requirements.py [--base-ref BASE_REF]

Example:
    ./bin/check_build_requirements.py --base-ref origin/main
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add lib to path
sys.path.insert(0, str(Path(__file__).parent / "lib"))

from lib.build_check import (
    analyze_git_diff,
    format_result_for_pr_comment,
    get_available_builder_images,
    get_misc_builder_scripts,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check if PR additions require building compilers or tools")
    parser.add_argument(
        "--base-ref",
        default="origin/main",
        help="Git ref to compare against (default: origin/main)",
    )
    parser.add_argument(
        "--yaml-dir",
        default="bin/yaml",
        help="Path to YAML directory (default: bin/yaml)",
    )
    parser.add_argument(
        "--workflow-file",
        default=".github/workflows/bespoke-build.yaml",
        help="Path to bespoke-build workflow (default: .github/workflows/bespoke-build.yaml)",
    )
    args = parser.parse_args()

    yaml_dir = Path(args.yaml_dir)
    if not yaml_dir.exists():
        print(f"Error: YAML directory not found: {yaml_dir}", file=sys.stderr)
        return 1

    workflow_path = Path(args.workflow_file)
    available_images = get_available_builder_images(workflow_path)
    misc_scripts = get_misc_builder_scripts()

    result = analyze_git_diff(yaml_dir, args.base_ref)

    if result.has_build_requirements():
        print(format_result_for_pr_comment(result, available_images, misc_scripts))
    else:
        print("No build requirements detected for new additions.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
