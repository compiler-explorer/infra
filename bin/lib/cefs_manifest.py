#!/usr/bin/env python3
"""CEFS manifest creation and management utilities."""

from __future__ import annotations

import datetime
import logging
import subprocess
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

_LOGGER = logging.getLogger(__name__)


class ManifestContentEntry(BaseModel):
    """Represents a single entry in the manifest contents list."""

    name: str = Field(..., description="Full installable name (e.g., 'compilers/c++/x86/gcc 12.4.0')")
    destination: str = Field(..., description="NFS destination path")

    @field_validator("name")
    @classmethod
    def validate_name_format(cls, v: str) -> str:
        """Validate that name looks like a proper installable name."""
        if not v or v.isspace():
            raise ValueError("Name cannot be empty")

        # Must have exactly one space (separating name from version)
        if v.count(" ") != 1:
            raise ValueError(f"Invalid installable name '{v}': must have exactly one space between name and version")

        # Must have path structure (at least one /)
        if "/" not in v:
            raise ValueError(
                f"Invalid installable name '{v}': must have path structure like 'compilers/c++/x86/gcc 12.4.0'"
            )

        return v

    model_config = ConfigDict(extra="forbid")  # Reject unknown fields like 'target'


class CEFSManifest(BaseModel):
    """Represents a complete CEFS manifest."""

    version: int = Field(..., description="Manifest version")
    created_at: str = Field(..., description="ISO format creation timestamp")
    git_sha: str = Field(..., description="Git SHA of the code that created this")
    command: list[str] = Field(..., description="Command that created this image")
    description: str = Field(..., description="Human-readable description")
    operation: str = Field(..., description="Operation type: install, convert, or consolidate")
    contents: list[ManifestContentEntry] = Field(..., description="List of contents in this image")

    @field_validator("version")
    @classmethod
    def validate_version(cls, v: int) -> int:
        """Validate manifest version."""
        if v != 1:
            raise ValueError(f"Unsupported manifest version: {v}")
        return v

    @field_validator("operation")
    @classmethod
    def validate_operation(cls, v: str) -> str:
        """Validate operation type."""
        valid_operations = {"install", "convert", "consolidate"}
        if v not in valid_operations:
            raise ValueError(f"Invalid operation '{v}': must be one of {valid_operations}")
        return v

    model_config = ConfigDict(extra="forbid")  # Reject unknown fields


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


def sanitize_path_for_filename(path: Path) -> str:
    """Sanitize a path for use in filename by replacing problematic characters.

    Args:
        path: Path to sanitize

    Returns:
        Sanitized string safe for use in filenames
    """
    translation_table = str.maketrans("/ :?", "____")
    return str(path).strip("/").translate(translation_table)


def generate_cefs_filename(hash: str, operation: str, path: Path | None = None) -> str:
    """Generate a CEFS filename using the new naming convention.

    Args:
        hash: 24-character hash
        operation: Operation type ("install", "convert", "consolidate")
        path: Path information for suffix (optional)

    Returns:
        Generated filename with appropriate suffix

    Examples:
        >>> generate_cefs_filename("9da642f654bc890a12345678", "install", Path("/opt/compiler-explorer/gcc-15.1.0"))
        "9da642f654bc890a12345678_opt_compiler-explorer_gcc-15.1.0.sqfs"

        >>> generate_cefs_filename("abcdef1234567890abcdef12", "consolidate")
        "abcdef1234567890abcdef12_consolidated.sqfs"
    """
    if operation == "consolidate":
        suffix = "consolidated"
    elif operation == "convert" and path:
        meaningful_path = str(path).replace(".img", "")
        sanitized = sanitize_path_for_filename(Path(meaningful_path))
        suffix = f"converted_{sanitized}"
    elif path:
        suffix = sanitize_path_for_filename(path)
    else:
        suffix = operation

    return f"{hash}_{suffix}.sqfs"


def create_manifest(
    operation: str,
    description: str,
    contents: list[dict[str, str]],
    command: list[str] | None = None,
) -> dict[str, Any]:
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
        ...     description="Created through installation of compilers/c++/x86/gcc 15.1.0",
        ...     contents=[{
        ...         "name": "compilers/c++/x86/gcc 15.1.0",
        ...         "destination": "/opt/compiler-explorer/gcc-15.1.0"
        ...     }]
        ... )
    """
    if command is None:
        command = sys.argv.copy()

    manifest = {
        "version": 1,
        "created_at": datetime.datetime.now(datetime.UTC).isoformat(),
        "git_sha": get_git_sha(),
        "command": command,
        "description": description,
        "operation": operation,
        "contents": contents,
    }

    return manifest


def write_manifest_alongside_image(manifest: dict[str, Any], image_path: Path) -> None:
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


def write_manifest_inprogress(manifest: dict[str, Any], image_path: Path) -> None:
    """Write manifest as .yaml.inprogress to indicate incomplete operation.

    This creates a temporary manifest file that signals an in-progress operation.
    The file should be renamed to .yaml after all operations complete successfully.

    Args:
        manifest: Manifest dictionary
        image_path: Path to the .sqfs image file
    """
    inprogress_path = Path(str(image_path.with_suffix(".yaml")) + ".inprogress")

    _LOGGER.debug("Writing in-progress manifest: %s", inprogress_path)
    inprogress_path.parent.mkdir(parents=True, exist_ok=True)

    with open(inprogress_path, "w", encoding="utf-8") as f:
        yaml.dump(manifest, f, default_flow_style=False, sort_keys=False)


def finalize_manifest(image_path: Path) -> None:
    """Finalize manifest by renaming .yaml.inprogress to .yaml.

    This atomic rename indicates that all operations have completed successfully
    and the image is safe to use (and safe from GC).

    Args:
        image_path: Path to the .sqfs image file

    Raises:
        FileNotFoundError: If .yaml.inprogress file doesn't exist
        OSError: If rename fails
    """
    inprogress_path = Path(str(image_path.with_suffix(".yaml")) + ".inprogress")
    final_path = image_path.with_suffix(".yaml")

    if not inprogress_path.exists():
        raise FileNotFoundError(f"In-progress manifest not found: {inprogress_path}")

    _LOGGER.debug("Finalizing manifest: %s -> %s", inprogress_path, final_path)
    inprogress_path.rename(final_path)


def validate_manifest(manifest_dict: dict[str, Any]) -> CEFSManifest:
    """Validate a manifest dictionary against the Pydantic model.

    Args:
        manifest_dict: Raw manifest dictionary

    Returns:
        Validated CEFSManifest object

    Raises:
        ValueError: If manifest is invalid
    """
    try:
        return CEFSManifest(**manifest_dict)
    except Exception as e:
        raise ValueError(f"Invalid manifest: {e}") from e


def read_manifest_from_alongside(image_path: Path) -> dict[str, Any] | None:
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
        with open(manifest_path, encoding="utf-8") as f:
            manifest_dict = yaml.safe_load(f)

        # Validate the manifest
        validate_manifest(manifest_dict)
        return manifest_dict
    except ValueError as e:
        _LOGGER.error("Invalid manifest in %s: %s", manifest_path, e)
        raise
    except OSError as e:
        _LOGGER.error("Failed to read manifest file %s: %s", manifest_path, e)
        raise
    except yaml.YAMLError as e:
        _LOGGER.error("Invalid YAML in manifest file %s: %s", manifest_path, e)
        raise


def create_installable_manifest_entry(installable_name: str, destination_path: Path) -> dict[str, str]:
    """Create manifest entry from installable information.

    Args:
        installable_name: Full installable name including version (e.g., "compilers/c++/x86/gcc 10.1.0")
        destination_path: Full NFS destination path

    Returns:
        Dictionary with name and destination fields

    Example:
        >>> create_installable_manifest_entry("compilers/c++/x86/gcc 10.1.0", Path("/opt/compiler-explorer/gcc-10.1.0"))
        {"name": "compilers/c++/x86/gcc 10.1.0", "destination": "/opt/compiler-explorer/gcc-10.1.0"}
    """
    return {
        "name": installable_name,
        "destination": str(destination_path),
    }
