#!/usr/bin/env python3
"""CEFS output formatting and display utilities."""

from __future__ import annotations

import logging
from pathlib import Path

import humanfriendly
import yaml
from lib.cefs.consolidation import (
    get_consolidated_item_status,
    group_images_by_usage,
    is_consolidated_image,
    is_item_still_using_image,
)
from lib.cefs.paths import describe_cefs_image, get_current_symlink_targets
from lib.cefs.state import CEFSState
from lib.cefs_manifest import read_manifest_from_alongside

_LOGGER = logging.getLogger(__name__)


def get_image_description_from_manifest(image_path: Path) -> list[str] | None:
    """Extract content names from an image's manifest file.

    Args:
        image_path: Path to the CEFS image

    Returns:
        List of content names or None if manifest unavailable/invalid
    """
    try:
        manifest = read_manifest_from_alongside(image_path)
        if manifest and "contents" in manifest:
            names = []
            for content in manifest["contents"]:
                if "name" in content:
                    names.append(content["name"])
            return names if names else None
        return None
    except (OSError, yaml.YAMLError):
        return None


def get_image_description(image_path: Path, cefs_mount_point: Path) -> list[str] | None:
    """Get description of image contents from manifest or by mounting.

    First tries to read from manifest, then falls back to mounting the image.

    Args:
        image_path: Path to the CEFS image
        cefs_mount_point: Base mount point for CEFS

    Returns:
        List of content names or None if unable to determine
    """
    # Try manifest first
    names = get_image_description_from_manifest(image_path)
    if names:
        return names

    # Fallback to mounting
    filename_stem = image_path.stem
    # Extract just the hash part for describe_cefs_image
    hash_part = filename_stem.split("_")[0] if "_" in filename_stem else filename_stem
    try:
        contents = describe_cefs_image(hash_part, cefs_mount_point)
        return contents if contents else None
    except OSError:
        return None


def format_image_contents_string(names: list[str] | None, max_items: int) -> str:
    """Format a list of content names for display.

    Args:
        names: List of content names or None
        max_items: Maximum number of items to show before truncating

    Returns:
        Formatted string like "[contains: name1, name2, ...]" or empty string
    """
    if not names:
        return ""

    if len(names) <= max_items:
        return f" [contains: {', '.join(names)}]"
    else:
        shown = names[:max_items]
        return f" [contains: {', '.join(shown)}...]"


def format_verbose_image_details(
    image_path: Path,
    usage: float,
    items_info: list[str] | None,
    manifest: dict | None,
    mount_point: Path,
) -> list[str]:
    """Format verbose details for a partially used consolidated image.

    Args:
        image_path: Path to the image
        usage: Usage percentage
        items_info: List of item descriptions
        manifest: Manifest dictionary
        mount_point: CEFS mount point

    Returns:
        List of formatted lines
    """
    lines = []

    if not items_info:
        lines.append(f"        {image_path.name} ({usage:.1f}%)")
        return lines

    total_items = len(items_info)
    used_items = int(total_items * usage / 100)
    lines.append(f"        {image_path.name} ({usage:.1f}% - {used_items}/{total_items} items)")

    # Show what replaced each item if partially used
    if manifest and "contents" in manifest and usage < 100:
        for content in manifest["contents"]:
            if "destination" in content:
                dest_path = Path(content["destination"])
                targets = get_current_symlink_targets(dest_path)
                # Find which target (if any) points to this image for status reporting
                current_target = next(
                    (t for t in targets if is_item_still_using_image(t, image_path, mount_point)),
                    None,
                )
                status = get_consolidated_item_status(content, image_path, current_target, mount_point)
                if status:
                    lines.append(status)

    return lines


def format_usage_statistics(stats, state: CEFSState, verbose: bool, cefs_mount_point: Path) -> list[str]:
    """Format detailed usage statistics.

    Args:
        stats: Usage statistics object
        state: CEFSState object
        verbose: Whether to show verbose output
        cefs_mount_point: CEFS mount point

    Returns:
        List of formatted output lines
    """
    lines = []
    lines.append("\nImage Statistics:")
    lines.append(f"  Total images: {stats.total_images}")
    lines.append(f"  Individual images: {stats.individual_images}")
    lines.append(f"  Consolidated images: {stats.consolidated_images}")

    if stats.consolidated_images > 0:
        lines.append(f"    - Fully used (100%): {stats.fully_used_consolidated}")

        ranges = group_images_by_usage(stats.partially_used_consolidated)

        lines.append(f"    - Partially used: {len(stats.partially_used_consolidated)}")
        for range_name, images in ranges.items():
            if images:
                lines.append(f"      * {range_name} used: {len(images)} images")
                if verbose:
                    for image_path, usage in images:
                        items_info = get_image_description(image_path, cefs_mount_point)
                        manifest = read_manifest_from_alongside(image_path)
                        detail_lines = format_verbose_image_details(
                            image_path, usage, items_info, manifest, cefs_mount_point
                        )
                        lines.extend(detail_lines)

        # Count unused consolidated images
        unused_consolidated = len([p for p in stats.unused_images if is_consolidated_image(p)])
        lines.append(f"    - Unused (0%): {unused_consolidated}")

    lines.append("\nSpace Analysis:")
    lines.append(f"  Total CEFS space: {humanfriendly.format_size(stats.total_space, binary=True)}")
    if stats.wasted_space_estimate > 0:
        lines.append(
            f"  Wasted in partial images: ~{humanfriendly.format_size(stats.wasted_space_estimate, binary=True)} (estimated)"
        )

    small_consolidated = state.find_small_consolidated_images(5 * 1024 * 1024 * 1024)
    if small_consolidated:
        lines.append(f"  Potential consolidation: {len(small_consolidated)} small consolidated images could be merged")

    if verbose:
        lines.append("\nRun 'ce cefs consolidate --reconsolidate' to optimize partially used images")

    return lines


def get_installable_current_locations(image_path: Path) -> list[str]:
    """Get information about where each Installable in an image is currently installed."""
    if not (manifest := read_manifest_from_alongside(image_path)):
        return []

    def _classify(path: Path) -> str:
        if path.is_symlink():
            try:
                return f"{path} -> {path.readlink()}"
            except OSError as e:
                return f"{path} -> [unreadable: {e}]"
        if path.is_dir():
            return f"{path} [directory]"
        if path.exists():
            return f"{path} [file]"
        return "NOT INSTALLED"

    return [
        f"    └─ {content['name']} → currently: {_classify(Path(content['destination']))}"
        for content in manifest["contents"]
    ]
