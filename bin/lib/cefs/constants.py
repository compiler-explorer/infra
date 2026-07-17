#!/usr/bin/env python3
"""Shared constants for CEFS operations."""

from __future__ import annotations

# NFS performance tuning
NFS_MAX_RECURSION_DEPTH = 3  # Limit depth when recursing on NFS to avoid performance issues

# Default minimum age for CEFS cleanup operations
DEFAULT_MIN_AGE = "1h"
