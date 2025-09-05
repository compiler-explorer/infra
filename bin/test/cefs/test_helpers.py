#!/usr/bin/env python3
"""Helper functions for CEFS tests."""

from __future__ import annotations

import datetime


def make_test_manifest(**kwargs) -> dict:
    """Create a test manifest with sensible defaults.

    Args:
        **kwargs: Override any default manifest fields

    Returns:
        Complete manifest dictionary
    """
    defaults = {
        "version": 1,
        "operation": "install",
        "description": "Test manifest",
        "contents": [],
        "created_at": datetime.datetime.now(datetime.UTC).isoformat(),
        "git_sha": "test_sha",
        "command": ["test", "command"],
    }
    defaults.update(kwargs)
    return defaults
