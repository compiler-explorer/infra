#!/usr/bin/env python3
"""Data models for CEFS operations."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class ConsolidationCandidate:
    """Represents an item that can be consolidated."""

    name: str
    nfs_path: Path
    squashfs_path: Path
    size: int
    extraction_path: Path = field(default_factory=lambda: Path("."))
    from_reconsolidation: bool = False


@dataclass(frozen=True)
class ImageUsageStats:
    """Statistics about CEFS image usage."""

    total_images: int
    individual_images: int
    consolidated_images: int
    fully_used_consolidated: int
    partially_used_consolidated: list[tuple[Path, float]]  # (path, usage_percentage)
    unused_images: list[Path]
    total_space: int
    wasted_space_estimate: int
