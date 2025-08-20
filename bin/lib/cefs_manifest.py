#!/usr/bin/env python3
"""CEFS manifest creation and management utilities."""

import datetime
import logging
import subprocess
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

_LOGGER = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_git_sha() -> str:
    """Get the current git SHA, cached to avoid repeated subprocess calls.

    Uses git -C to ensure we're checking the correct repository even if
    ce_install is run from another directory.

    Returns:
        Git SHA string, or "unknown" if git command fails
    """
    try:
        project_root = Path(__file__).parent.parent.parent
        result = subprocess.run(
            ["git", "-C", str(project_root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        else:
            _LOGGER.warning("Git command failed: %s", result.stderr.strip())
            return "unknown"
    except (subprocess.TimeoutExpired, OSError) as e:
        _LOGGER.warning("Failed to get git SHA: %s", e)
        return "unknown"


def sanitize_path_for_filename(path: str) -> str:
    """Sanitize a path for use in filename by replacing problematic characters.

    Args:
        path: Path string to sanitize

    Returns:
        Sanitized string safe for use in filenames
    """
    sanitized = path.strip("/").replace("/", "_")
    sanitized = sanitized.replace(" ", "_").replace(":", "_").replace("?", "_")
    return sanitized


def generate_cefs_filename(hash: str, operation: str, path: str = "") -> str:
    """Generate a CEFS filename using the new naming convention.

    Args:
        hash: 24-character hash
        operation: Operation type ("install", "convert", "consolidate")
        path: Path information for suffix (optional)

    Returns:
        Generated filename with appropriate suffix

    Examples:
        >>> generate_cefs_filename("9da642f654bc890a12345678", "install", "/opt/compiler-explorer/gcc-15.1.0")
        "9da642f654bc890a12345678_opt_compiler-explorer_gcc-15.1.0.sqfs"

        >>> generate_cefs_filename("abcdef1234567890abcdef12", "consolidate")
        "abcdef1234567890abcdef12_consolidated.sqfs"
    """
    if operation == "consolidate":
        suffix = "consolidated"
    elif operation == "convert":
        if path:
            meaningful_path = path.replace("/efs/squash-images/", "").replace(".img", "")
            sanitized = sanitize_path_for_filename(meaningful_path)
            suffix = f"converted_{sanitized}"
        else:
            suffix = "converted"
    elif operation == "install":
        if path:
            sanitized = sanitize_path_for_filename(path)
            suffix = sanitized
        else:
            suffix = "install"
    else:
        suffix = operation

    return f"{hash}_{suffix}.sqfs"


def create_manifest(
    operation: str,
    description: str,
    contents: List[Dict[str, str]],
    command: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Create a manifest dictionary for a CEFS image.

    Args:
        operation: Type of operation ("install", "convert", "consolidate")
        description: Human-readable description of what this image contains
        contents: List of installable contents, each with name, target, destination
        command: Command-line that created this image (defaults to sys.argv)

    Returns:
        Manifest dictionary ready for YAML serialization

    Example:
        >>> manifest = create_manifest(
        ...     operation="install",
        ...     description="Created through installation of gcc-15.1.0",
        ...     contents=[{
        ...         "name": "compilers/c++/x86/gcc",
        ...         "target": "15.1.0",
        ...         "destination": "/opt/compiler-explorer/gcc-15.1.0"
        ...     }]
        ... )
    """
    if command is None:
        command = sys.argv.copy()

    manifest = {
        "version": 1,
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "git_sha": get_git_sha(),
        "command": command,
        "description": description,
        "operation": operation,
        "contents": contents,
    }

    return manifest


def write_manifest_to_directory(manifest: Dict[str, Any], directory: Path) -> None:
    """Write manifest as manifest.yaml to a directory.

    This is used when we want to include the manifest inside a squashfs image.

    Args:
        manifest: Manifest dictionary
        directory: Directory to write manifest.yaml into
    """
    directory.mkdir(parents=True, exist_ok=True)
    manifest_path = directory / "manifest.yaml"

    _LOGGER.debug("Writing manifest to %s", manifest_path)
    with open(manifest_path, "w", encoding="utf-8") as f:
        yaml.dump(manifest, f, default_flow_style=False, sort_keys=False)


def write_manifest_alongside_image(manifest: Dict[str, Any], image_path: Path) -> None:
    """Write manifest as manifest.yaml alongside a CEFS image file.

    This creates a manifest file next to the .sqfs file for easy access
    without mounting the image.

    Args:
        manifest: Manifest dictionary
        image_path: Path to the .sqfs image file
    """
    manifest_path = image_path.with_suffix(".yaml")

    _LOGGER.debug("Writing manifest alongside image: %s", manifest_path)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    with open(manifest_path, "w", encoding="utf-8") as f:
        yaml.dump(manifest, f, default_flow_style=False, sort_keys=False)


def read_manifest_from_alongside(image_path: Path) -> Optional[Dict[str, Any]]:
    """Read manifest from the .yaml file alongside a CEFS image.

    Args:
        image_path: Path to the .sqfs image file

    Returns:
        Manifest dictionary or None if not found/invalid
    """
    manifest_path = image_path.with_suffix(".yaml")

    if not manifest_path.exists():
        return None

    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except (OSError, yaml.YAMLError) as e:
        _LOGGER.warning("Failed to read manifest from %s: %s", manifest_path, e)
        return None


def extract_installable_info_from_path(install_path: str, nfs_path: Path) -> Dict[str, str]:
    """Extract installable information from installation path for manifest contents.

    This is a best-effort function to create reasonable name/target/destination
    entries for the manifest when we don't have full installable metadata.

    Args:
        install_path: Relative installation path (e.g., "gcc-15.1.0")
        nfs_path: Full NFS destination path

    Returns:
        Dictionary with name, target, destination fields
    """
    parts = install_path.split("-")
    if len(parts) >= 2:
        name = "-".join(parts[:-1])
        target = parts[-1]
    else:
        name = install_path
        target = "unknown"

    return {
        "name": name,
        "target": target,
        "destination": str(nfs_path),
    }
