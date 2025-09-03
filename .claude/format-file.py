#!/usr/bin/env python3
"""Run pre-commit hooks on files after Claude edits them."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def main() -> int:
    """Process stdin JSON and run pre-commit on Python files."""
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        # Silent exit for malformed input
        return 0

    # Extract file_path from JSON (try both possible locations)
    file_path = None
    if "tool_input" in data and "file_path" in data["tool_input"]:
        file_path = data["tool_input"]["file_path"]
    elif "tool_response" in data and "filePath" in data["tool_response"]:
        file_path = data["tool_response"]["filePath"]

    if not file_path:
        return 0

    path = Path(file_path)

    # Only process Python files
    if path.suffix != ".py":
        return 0

    # Check if file exists
    if not path.exists():
        return 0

    # Run specific pre-commit hooks on the file
    hooks = ["trailing-whitespace", "end-of-file-fixer", "mixed-line-ending", "ruff-format"]
    for hook in hooks:
        try:
            subprocess.run(
                ["pre-commit", "run", hook, "--files", str(path)],
                check=False,  # Don't raise on non-zero exit
                capture_output=True,  # Suppress output for silent operation
                text=True,
            )
        except (subprocess.SubprocessError, FileNotFoundError):
            # Silent failure - pre-commit might not be installed
            pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
