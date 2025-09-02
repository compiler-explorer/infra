#!/usr/bin/env python3
"""CEFS (Compiler Explorer FileSystem) v2 utility functions."""

from __future__ import annotations

import datetime
import hashlib
import logging
import os
import shutil
import tempfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import humanfriendly
import yaml

from .cefs_manifest import (
    generate_cefs_filename,
    read_manifest_from_alongside,
    write_manifest_inprogress,
)
from .config import SquashfsConfig
from .squashfs import create_squashfs_image, extract_squashfs_image

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class CEFSPaths:
    """Container for CEFS image path and mount path."""

    image_path: Path
    mount_path: Path


def get_cefs_image_path(image_dir: Path, filename: str) -> Path:
    """Get the full CEFS image path for a given filename.

    Args:
        image_dir: Base image directory (e.g., Path("/efs/cefs-images"))
        filename: Complete filename with descriptive suffix

    Returns:
        Full path to the CEFS image file (e.g., /efs/cefs-images/a1/a1b2c3d4....sqfs)
    """
    return image_dir / filename[:2] / filename


def get_cefs_mount_path(mount_point: Path, filename: str) -> Path:
    """Get the full CEFS mount target path for a given hash.

    Args:
        mount_point: Base mount point (e.g., Path("/cefs"))
        filename: Complete filename with descriptive suffix

    Returns:
        Full path to the CEFS mount target (e.g., {mount_point}/a1/a1b2c3d4...)
    """
    return mount_point / filename[:2] / Path(filename).with_suffix("")


def get_cefs_paths(image_dir: Path, mount_point: Path, filename: str) -> CEFSPaths:
    """Get both CEFS image path and mount path for a given filename.

    Args:
        image_dir: Base image directory (e.g., Path("/efs/cefs-images"))
        mount_point: Base mount point (e.g., Path("/cefs"))
        filename: Complete filename with descriptive suffix

    Returns:
        CEFSPaths containing both image_path and mount_path
    """
    return CEFSPaths(
        image_path=get_cefs_image_path(image_dir, filename),
        mount_path=get_cefs_mount_path(mount_point, filename),
    )


def calculate_squashfs_hash(squashfs_path: Path) -> str:
    """Calculate SHA256 hash of squashfs image using Python hashlib."""
    sha256_hash = hashlib.sha256()
    file_size = squashfs_path.stat().st_size
    _LOGGER.debug("Calculating hash for %s (size: %d bytes)", squashfs_path, file_size)
    with open(squashfs_path, "rb") as f:
        for chunk in iter(lambda: f.read(16 * 1024 * 1024), b""):
            sha256_hash.update(chunk)
    full_hash = sha256_hash.hexdigest()
    truncated_hash = full_hash[:24]
    _LOGGER.debug("Hash for %s: full=%s, truncated=%s", squashfs_path, full_hash, truncated_hash)
    return truncated_hash


def get_cefs_filename_for_image(squashfs_path: Path, operation: str, path: Path | None = None) -> str:
    """Generate CEFS filename by calculating hash and adding suffix.

    Combines hash calculation and filename generation into a single operation.

    Args:
        squashfs_path: Path to squashfs image to hash
        operation: Operation type ("install", "convert", "consolidate")
        path: Optional path for suffix generation

    Returns:
        Generated filename with hash and descriptive suffix

    Raises:
        OSError: If unable to read the squashfs file
    """
    hash_value = calculate_squashfs_hash(squashfs_path)
    return generate_cefs_filename(hash_value, operation, path)


def detect_nfs_state(nfs_path: Path) -> str:
    """Detect current state: 'symlink', 'directory', or 'missing'."""
    if nfs_path.is_symlink():
        return "symlink"
    elif nfs_path.exists():
        return "directory"
    else:
        return "missing"


def validate_cefs_mount_point(mount_point: Path) -> bool:
    """Validate that CEFS mount point is accessible.

    Args:
        mount_point: CEFS mount point path (e.g., Path("/cefs"))

    Returns:
        True if mount point is accessible, False otherwise
    """
    mount_path = mount_point

    if not mount_path.exists():
        _LOGGER.error("CEFS mount point does not exist: %s", mount_point)
        return False

    if not mount_path.is_dir():
        _LOGGER.error("CEFS mount point is not a directory: %s", mount_point)
        return False

    # Try to access the mount point (this will trigger autofs if configured)
    try:
        list(mount_path.iterdir())
        return True
    except PermissionError:
        _LOGGER.error("No permission to access CEFS mount point: %s", mount_point)
        return False
    except OSError as e:
        _LOGGER.error("Cannot access CEFS mount point %s: %s", mount_point, e)
        return False


def get_directory_size(directory: Path) -> int:
    """Calculate total size of a directory tree in bytes.

    Args:
        directory: Directory to measure

    Returns:
        Total size in bytes
    """
    total_size = 0
    try:
        for item in directory.rglob("*"):
            if item.is_file() and not item.is_symlink():
                total_size += item.stat().st_size
    except OSError as e:
        _LOGGER.warning("Error calculating directory size for %s: %s", directory, e)
    return total_size


def copy_to_cefs_atomically(source_path: Path, cefs_image_path: Path) -> None:
    """Copy a file to CEFS images directory using atomic rename.

    Creates a uniquely named temp file and atomically renames it to ensure
    we never have truncated .sqfs files in the CEFS directory.

    Args:
        source_path: Source squashfs image to copy
        cefs_image_path: Target path in CEFS images directory

    Raises:
        Exception: If copy fails (temp file is cleaned up)
    """
    _LOGGER.info("Copying %s to %s", source_path, cefs_image_path)
    cefs_image_path.parent.mkdir(parents=True, exist_ok=True)

    # SAFETY: Create uniquely named temp file in same directory for atomic rename
    # This ensures that partially copied files never have the .sqfs extension
    # and thus can never be mistaken for complete images by GC or other operations
    with tempfile.NamedTemporaryFile(
        dir=cefs_image_path.parent, suffix=".tmp", prefix="cefs_", delete=False
    ) as temp_file:
        temp_path = Path(temp_file.name)
        with open(source_path, "rb") as source_file:
            shutil.copyfileobj(source_file, temp_file, length=1024 * 1024)
    try:
        # Atomic rename - only complete files get .sqfs extension
        # On Linux, rename() is atomic within the same filesystem
        temp_path.replace(cefs_image_path)
    except Exception:
        # Clean up temp file on any failure
        temp_path.unlink(missing_ok=True)
        raise


def deploy_to_cefs_with_manifest(source_path: Path, cefs_image_path: Path, manifest: dict) -> None:
    """Deploy an image to CEFS with its manifest.

    Uses .yaml.inprogress pattern to prevent race conditions:
    1. Copy squashfs image atomically
    2. Write manifest as .yaml.inprogress (operation incomplete)
    3. Caller creates symlinks
    4. Caller must call finalize_manifest() after symlinks are created

    Args:
        source_path: Source squashfs image to deploy
        cefs_image_path: Target path in CEFS images directory
        manifest: Manifest dictionary to write alongside the image

    Raises:
        Exception: If deployment fails (all files are cleaned up)
    """
    copy_to_cefs_atomically(source_path, cefs_image_path)
    write_manifest_inprogress(manifest, cefs_image_path)


def backup_and_symlink(nfs_path: Path, cefs_target: Path, dry_run: bool, defer_cleanup: bool) -> None:
    """Backup NFS directory and create CEFS symlink with rollback on failure.

    Args:
        nfs_path: Path to the NFS directory to backup and replace with symlink
        cefs_target: Target path for the CEFS symlink
        dry_run: If True, only log what would be done
        defer_cleanup: If True, rename old .bak to .DELETE_ME_<timestamp> instead of deleting
    """
    backup_path = nfs_path.with_name(nfs_path.name + ".bak")

    if dry_run:
        _LOGGER.info("Would backup %s to %s", nfs_path, backup_path)
        _LOGGER.info("Would create symlink %s -> %s", nfs_path, cefs_target)
        return

    try:
        # Handle old backup if it exists
        if backup_path.exists():
            if defer_cleanup:
                # Rename to .DELETE_ME_<timestamp> for later cleanup
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                delete_me_path = nfs_path.with_name(f"{nfs_path.name}.DELETE_ME_{timestamp}")
                backup_path.rename(delete_me_path)
                _LOGGER.info("Renamed old backup %s to %s for deferred cleanup", backup_path, delete_me_path)
            else:
                # Original behavior: delete immediately
                if backup_path.is_dir():
                    shutil.rmtree(backup_path)
                else:
                    backup_path.unlink()

        # Backup current directory (or symlink) if it exists. Follow symlinks=False here to account for broken symlinks
        if nfs_path.exists(follow_symlinks=False):
            nfs_path.rename(backup_path)
            _LOGGER.info("Backed up %s to %s", nfs_path, backup_path)

        # Create symlink
        nfs_path.symlink_to(cefs_target, target_is_directory=True)
        _LOGGER.info("Created symlink %s -> %s", nfs_path, cefs_target)

    except OSError as e:
        # Rollback on failure
        if backup_path.exists():
            nfs_path.unlink(missing_ok=True)
            backup_path.rename(nfs_path)
            _LOGGER.error("Rollback: restored %s from backup", nfs_path)
        raise RuntimeError(f"Failed to create symlink: {e}") from e


def has_enough_space(available_bytes: int, required_bytes: int) -> bool:
    """Pure function to check if available space meets requirements.

    Args:
        available_bytes: Available space in bytes
        required_bytes: Required space in bytes

    Returns:
        True if enough space is available
    """
    return available_bytes >= required_bytes


def check_temp_space_available(temp_dir: Path, required_bytes: int) -> bool:
    """Check if temp directory has enough space for consolidation.

    Args:
        temp_dir: Directory to check space for
        required_bytes: Required space in bytes

    Returns:
        True if enough space is available
    """
    try:
        stat = os.statvfs(temp_dir)
        available_bytes = stat.f_bavail * stat.f_frsize
        _LOGGER.debug("Available space: %d bytes, required: %d bytes", available_bytes, required_bytes)
        return has_enough_space(available_bytes, required_bytes)
    except OSError as e:
        _LOGGER.error("Failed to check disk space for %s: %s", temp_dir, e)
        return False


def snapshot_symlink_targets(symlink_paths: list[Path]) -> dict[Path, Path]:
    """Snapshot current symlink targets for race condition detection.

    Args:
        symlink_paths: List of symlink paths to snapshot

    Returns:
        Dictionary mapping symlink path to current target
    """
    snapshot = {}
    for symlink_path in symlink_paths:
        try:
            if symlink_path.is_symlink():
                snapshot[symlink_path] = symlink_path.readlink()
                _LOGGER.debug("Snapshotted %s -> %s", symlink_path, snapshot[symlink_path])
        except OSError as e:
            _LOGGER.warning("Failed to read symlink %s: %s", symlink_path, e)
    return snapshot


def verify_symlinks_unchanged(snapshot: dict[Path, Path]) -> tuple[list[Path], list[Path]]:
    """Verify symlinks haven't changed since snapshot.

    Args:
        snapshot: Dictionary of symlink path to expected target

    Returns:
        Tuple of (unchanged_symlinks, changed_symlinks)
    """
    unchanged = []
    changed = []

    for symlink_path, expected_target in snapshot.items():
        try:
            if symlink_path.is_symlink():
                current_target = symlink_path.readlink()
                if current_target == expected_target:
                    unchanged.append(symlink_path)
                else:
                    changed.append(symlink_path)
                    _LOGGER.warning(
                        "Symlink changed during consolidation: %s (was: %s, now: %s)",
                        symlink_path,
                        expected_target,
                        current_target,
                    )
            else:
                changed.append(symlink_path)
                _LOGGER.warning("Symlink no longer exists: %s", symlink_path)
        except OSError as e:
            changed.append(symlink_path)
            _LOGGER.warning("Failed to read symlink %s: %s", symlink_path, e)

    return unchanged, changed


def _extract_single_squashfs(args: tuple[str, str, str, str | None, str, str]) -> dict[str, Any]:
    """Worker function to extract a single squashfs image.

    Args are serialized as strings for pickling:
        unsquashfs_path, squashfs_path, subdir_path, extraction_path, subdir_name, nfs_path

    Returns:
        Dictionary with extraction metrics and status
    """
    # Set up logging for worker process
    logger = logging.getLogger(__name__)

    # Unpack and convert arguments back from strings
    unsquashfs_path, squashfs_path_str, subdir_path_str, extraction_path_str, subdir_name, nfs_path_str = args

    squashfs_path = Path(squashfs_path_str)
    subdir_path = Path(subdir_path_str)
    extraction_path = Path(extraction_path_str) if extraction_path_str else None

    # Create minimal config for extraction
    config = SquashfsConfig(
        mksquashfs_path="",  # Not needed for extraction
        unsquashfs_path=unsquashfs_path,
        compression="",  # Not needed for extraction
        compression_level=0,  # Not needed for extraction
    )

    try:
        compressed_size = squashfs_path.stat().st_size

        logger.info(
            "Extracting %s (%s) from %s to %s",
            squashfs_path,
            humanfriendly.format_size(compressed_size, binary=True),
            extraction_path,
            subdir_path,
        )

        extract_squashfs_image(config, squashfs_path, subdir_path, extraction_path)

        # Measure extracted size
        extracted_size = get_directory_size(subdir_path)

        compression_ratio = extracted_size / compressed_size if compressed_size > 0 else 0

        logger.info(
            "Extracted %s -> %s (%.1fx compression)",
            humanfriendly.format_size(compressed_size, binary=True),
            humanfriendly.format_size(extracted_size, binary=True),
            compression_ratio,
        )

        return {
            "success": True,
            "nfs_path": nfs_path_str,
            "subdir_name": subdir_name,
            "compressed_size": compressed_size,
            "extracted_size": extracted_size,
            "compression_ratio": compression_ratio,
        }
    except Exception as e:
        logger.error("Failed to extract %s: %s", squashfs_path, e)
        return {
            "success": False,
            "nfs_path": nfs_path_str,
            "subdir_name": subdir_name,
            "error": str(e),
        }


def create_consolidated_image(
    squashfs_config: SquashfsConfig,
    items: list[tuple[Path, Path, str, Path]],
    temp_dir: Path,
    output_path: Path,
    max_parallel_extractions: int | None = None,
) -> None:
    """Create a consolidated squashfs image from multiple CEFS items.

    Args:
        squashfs_config: SquashFsConfig object with tool paths and settings
        items: List of (nfs_path, squashfs_path, subdirectory_name, extraction_path) tuples
        temp_dir: Temporary directory for extraction
        output_path: Path for the consolidated squashfs image
        max_parallel_extractions: Maximum number of parallel extractions (default: CPU count)

    Raises:
        RuntimeError: If consolidation fails
    """
    extraction_dir = temp_dir / "extract"
    extraction_dir.mkdir(parents=True, exist_ok=True)

    # Determine number of workers
    if max_parallel_extractions is None:
        max_parallel_extractions = os.cpu_count() or 1
    num_workers = min(max_parallel_extractions, len(items))

    _LOGGER.info("Starting parallel extraction with %d workers for %d items", num_workers, len(items))

    try:
        # Prepare extraction tasks (serialize paths as strings for pickling)
        extraction_tasks = []
        for nfs_path, squashfs_path, subdir_name, extraction_path in items:
            subdir_path = extraction_dir / subdir_name
            args = (
                squashfs_config.unsquashfs_path,
                str(squashfs_path),
                str(subdir_path),
                str(extraction_path) if extraction_path else None,
                subdir_name,
                str(nfs_path),
            )
            extraction_tasks.append(args)

        # Extract squashfs images in parallel
        total_compressed_size = 0
        total_extracted_size = 0
        failed_extractions = []

        with ProcessPoolExecutor(max_workers=num_workers) as executor:
            # Submit all extraction tasks
            future_to_args = {executor.submit(_extract_single_squashfs, args): args for args in extraction_tasks}

            # Process results as they complete
            completed = 0
            for future in as_completed(future_to_args):
                completed += 1
                result = future.result()

                if result["success"]:
                    total_compressed_size += result["compressed_size"]
                    total_extracted_size += result["extracted_size"]
                    _LOGGER.info(
                        "[%d/%d] Completed extraction of %s",
                        completed,
                        len(items),
                        result["subdir_name"],
                    )
                else:
                    failed_extractions.append(result)
                    _LOGGER.error(
                        "[%d/%d] Failed to extract %s: %s",
                        completed,
                        len(items),
                        result["subdir_name"],
                        result.get("error", "Unknown error"),
                    )

        # Check for failures
        if failed_extractions:
            raise RuntimeError(
                f"Failed to extract {len(failed_extractions)} of {len(items)} squashfs images: "
                + ", ".join(f["subdir_name"] for f in failed_extractions)
            )

        # Log total extraction summary
        total_compression_ratio = total_extracted_size / total_compressed_size if total_compressed_size > 0 else 0
        _LOGGER.info(
            "Total extraction: %s -> %s (%.1fx compression)",
            humanfriendly.format_size(total_compressed_size, binary=True),
            humanfriendly.format_size(total_extracted_size, binary=True),
            total_compression_ratio,
        )

        # Create consolidated squashfs image
        _LOGGER.info("Creating consolidated squashfs image at %s", output_path)
        create_squashfs_image(squashfs_config, extraction_dir, output_path)

        # Log final consolidation compression ratio
        consolidated_size = output_path.stat().st_size
        final_compression_ratio = total_extracted_size / consolidated_size if consolidated_size > 0 else 0

        # Calculate space savings vs original and total compression
        space_savings_ratio = total_compressed_size / consolidated_size if consolidated_size > 0 else 0
        total_compression_ratio = total_extracted_size / consolidated_size if consolidated_size > 0 else 0

        _LOGGER.info("Consolidation complete:")
        _LOGGER.info(
            "  Final image: %s (%.1fx compression of extracted data)",
            humanfriendly.format_size(consolidated_size, binary=True),
            final_compression_ratio,
        )
        _LOGGER.info(
            "  Space comparison: %s -> %s (%.1fx space savings)",
            humanfriendly.format_size(total_compressed_size, binary=True),
            humanfriendly.format_size(consolidated_size, binary=True),
            space_savings_ratio,
        )
        _LOGGER.info(
            "  Total compression: %s -> %s (%.1fx overall compression)",
            humanfriendly.format_size(total_extracted_size, binary=True),
            humanfriendly.format_size(consolidated_size, binary=True),
            total_compression_ratio,
        )

    finally:
        # Clean up extraction directory
        if extraction_dir.exists():
            shutil.rmtree(extraction_dir)
            _LOGGER.debug("Cleaned up extraction directory: %s", extraction_dir)


def update_symlinks_for_consolidation(
    unchanged_symlinks: list[Path],
    consolidated_filename: str,
    mount_point: Path,
    subdir_mapping: dict[Path, str],
    defer_cleanup: bool,
) -> None:
    """Update symlinks to point to consolidated CEFS mount.

    Args:
        unchanged_symlinks: List of symlinks that are safe to update
        consolidated_filename: Filename of the consolidated image (e.g., HASH_consolidated.sqfs)
        mount_point: CEFS mount point
        subdir_mapping: Mapping of nfs_path to subdirectory name in consolidated image
        defer_cleanup: If True, rename old .bak to .DELETE_ME_<timestamp> instead of deleting

    Raises:
        RuntimeError: If symlink update fails
    """
    for symlink_path in unchanged_symlinks:
        if symlink_path not in subdir_mapping:
            _LOGGER.warning("No subdirectory mapping for %s, skipping", symlink_path)
            continue

        subdir_name = subdir_mapping[symlink_path]
        # New target: {mount_point}/XX/HASH_consolidated/subdir_name
        new_target = get_cefs_mount_path(mount_point, consolidated_filename) / subdir_name

        try:
            backup_and_symlink(symlink_path, new_target, dry_run=False, defer_cleanup=defer_cleanup)
            _LOGGER.info("Updated symlink %s -> %s", symlink_path, new_target)
        except RuntimeError as e:
            raise RuntimeError(f"Failed to update symlink {symlink_path}: {e}") from e


def parse_cefs_target(cefs_target: Path, cefs_image_dir: Path, mount_point: Path) -> tuple[Path, bool]:
    """Parse CEFS symlink target and return image path and consolidation status.

    Args:
        cefs_target: The symlink target (e.g., {mount_point}/XX/HASH or {mount_point}/XX/HASH/subdir)
        cefs_image_dir: Base directory for CEFS images (e.g., /efs/cefs-images)
        mount_point: CEFS mount point (e.g., /cefs)

    Returns:
        Tuple of (cefs_image_path, is_already_consolidated)

    Raises:
        ValueError: If the CEFS target format is invalid

    Examples:
        >>> parse_cefs_target(Path("/cefs/9d/9da642f654bc890a12345678"), Path("/efs/cefs-images"), Path("/cefs"))
        (Path("/efs/cefs-images/9d/9da642f654bc890a12345678_gcc.sqfs"), False)

        >>> parse_cefs_target(Path("/cefs/ab/abcdef1234567890abcdef12/gcc-4.5"), Path("/efs/cefs-images"), Path("/cefs"))
        (Path("/efs/cefs-images/ab/abcdef1234567890abcdef12_consolidated.sqfs"), True)
    """
    parts = cefs_target.parts
    mount_parts = mount_point.parts
    # Expected: mount_point parts + ('XX', 'HASH', ...) for {mount_point}/XX/HASH/...

    # Check that target starts with mount_point
    if len(parts) < len(mount_parts) + 2:  # Need at least mount_point + XX + HASH
        raise ValueError(f"Invalid CEFS target format: {cefs_target}")

    # Verify the target starts with the mount point
    if parts[: len(mount_parts)] != mount_parts:
        raise ValueError(f"CEFS target must start with {mount_point}: {cefs_target}")

    # Get XX and HASH parts after the mount point
    hash_prefix = parts[len(mount_parts)]  # XX
    hash = parts[len(mount_parts) + 1]  # 24-char hash

    image_dir_subdir = cefs_image_dir / hash_prefix
    matching_files = list(image_dir_subdir.glob(f"{hash}*.sqfs"))

    if not matching_files:
        raise ValueError(f"No CEFS image found for hash {hash} in {image_dir_subdir}")

    cefs_image_path = matching_files[0]

    # If there are more parts after the hash, it's already consolidated
    is_already_consolidated = len(parts) > len(mount_parts) + 2

    return cefs_image_path, is_already_consolidated


def describe_cefs_image(filename: str, cefs_mount_point: Path) -> list[str]:
    """Get top-level entries from a CEFS image by triggering autofs mount.

    Args:
        filename: The CEFS hash filename to describe
        cefs_mount_point: Base CEFS mount point

    Returns:
        List of top-level entry names in the CEFS image
    """
    cefs_path = get_cefs_mount_path(cefs_mount_point, filename)
    try:
        return [entry.name for entry in cefs_path.iterdir()]
    except OSError as e:
        _LOGGER.warning("Could not list contents of %s: %s", cefs_path, e)
        return []


class CEFSState:
    """Track CEFS images and their references for garbage collection using manifests."""

    def __init__(self, nfs_dir: Path, cefs_image_dir: Path, mount_point: Path):
        """Initialize CEFS state tracker.

        Args:
            nfs_dir: Base NFS directory (e.g., /opt/compiler-explorer)
            cefs_image_dir: CEFS images directory (e.g., /efs/cefs-images)
            mount_point: CEFS mount point (e.g., /cefs)
        """
        self.nfs_dir = nfs_dir
        self.cefs_image_dir = cefs_image_dir
        self.mount_point = mount_point
        self.all_cefs_images: dict[str, Path] = {}  # filename_stem -> image_path
        self.image_references: dict[str, list[Path]] = {}  # filename_stem -> list of expected symlink destinations
        self.referenced_images: set[str] = set()  # Set of filename_stems that have valid symlinks
        self.inprogress_images: list[Path] = []  # List of .yaml.inprogress files found
        self.broken_images: list[Path] = []  # Images without .yaml or .yaml.inprogress

    def scan_cefs_images_with_manifests(self) -> None:
        """Scan all CEFS images and read their manifests to determine expected references.

        CRITICAL: Images with .yaml.inprogress manifests are tracked but NEVER eligible for GC.
        """
        if not self.cefs_image_dir.exists():
            _LOGGER.warning("CEFS images directory does not exist: %s", self.cefs_image_dir)
            return

        for subdir in self.cefs_image_dir.iterdir():
            if subdir.is_dir():
                # First check for .yaml.inprogress files (incomplete operations)
                for inprogress_file in subdir.glob("*.yaml.inprogress"):
                    self.inprogress_images.append(inprogress_file)
                    _LOGGER.warning("Found in-progress manifest: %s", inprogress_file)

                for image_file in subdir.glob("*.sqfs"):
                    # Store by filename stem (includes hash and suffix)
                    filename_stem = image_file.stem

                    # SAFETY: Check if this image has an .yaml.inprogress file indicating incomplete operation
                    # This prevents deletion of images that are being installed/converted/consolidated
                    # even if the operation is taking a long time or has failed partway through
                    inprogress_path = Path(str(image_file.with_suffix(".yaml")) + ".inprogress")
                    if inprogress_path.exists():
                        # Skip this image - it has an incomplete operation
                        _LOGGER.info("Skipping image with in-progress operation: %s", image_file)
                        # Mark it as referenced so it won't be deleted
                        self.referenced_images.add(filename_stem)
                        continue

                    # Check for .yaml manifest
                    manifest_path = image_file.with_suffix(".yaml")
                    if not manifest_path.exists():
                        # No .yaml and no .yaml.inprogress - this is a broken image
                        self.broken_images.append(image_file)
                        _LOGGER.error(
                            "BROKEN IMAGE: %s has no manifest or inprogress marker - needs investigation", image_file
                        )
                        # Do NOT add to all_cefs_images or image_references
                        continue

                    self.all_cefs_images[filename_stem] = image_file

                    # Try to read manifest to get expected destinations
                    try:
                        manifest = read_manifest_from_alongside(image_file)
                        if manifest and "contents" in manifest:
                            destinations = []
                            for content in manifest["contents"]:
                                if "destination" in content:
                                    dest_path = Path(content["destination"])
                                    destinations.append(dest_path)
                            self.image_references[filename_stem] = destinations
                            _LOGGER.debug("Image %s expects %d symlinks", filename_stem, len(destinations))
                        else:
                            # Manifest exists but has no contents or is malformed
                            self.image_references[filename_stem] = []
                            _LOGGER.warning("Manifest for %s has no contents", filename_stem)
                    except Exception as e:
                        _LOGGER.warning("Failed to read manifest for %s: %s", image_file, e)
                        self.image_references[filename_stem] = []

    def check_symlink_references(self) -> None:
        """Check if expected symlinks exist and point to the correct CEFS images."""
        for filename_stem, expected_destinations in self.image_references.items():
            if not expected_destinations:
                # Image has empty manifest - this is an error condition like missing manifest
                image_path = self.all_cefs_images.get(filename_stem)
                if image_path:
                    self.broken_images.append(image_path)
                    # Mark as referenced so it won't be deleted
                    self.referenced_images.add(filename_stem)
                    _LOGGER.error("BROKEN IMAGE: %s has empty manifest - needs investigation", image_path)
                continue

            # Check if any expected symlink points to this image
            for dest_path in expected_destinations:
                if self._check_symlink_points_to_image(dest_path, filename_stem):
                    self.referenced_images.add(filename_stem)
                    break  # At least one valid reference found

    def _check_symlink_points_to_image(self, dest_path: Path, filename_stem: str) -> bool:
        """Check if a symlink at dest_path points to the given CEFS image.

        CRITICAL: Also checks .bak symlinks to protect rollback capability.

        Args:
            dest_path: Expected destination path for symlink
            filename_stem: The filename stem (hash + suffix) of the CEFS image

        Returns:
            True if symlink exists and points to this image (either main or .bak)
        """
        full_path = dest_path if dest_path.is_absolute() else self.nfs_dir / dest_path.relative_to(Path("/"))

        # Check main symlink
        if self._check_single_symlink(full_path, filename_stem):
            return True

        # CRITICAL: Also check .bak symlink to protect rollback capability
        # Users rely on 'ce cefs rollback' which swaps .bak with main symlink
        # If we deleted the image referenced by .bak, rollback would fail catastrophically
        bak_path = full_path.with_name(full_path.name + ".bak")
        if self._check_single_symlink(bak_path, filename_stem):
            _LOGGER.debug("Found reference via .bak symlink: %s", bak_path)
            return True

        return False

    def _check_single_symlink(self, symlink_path: Path, filename_stem: str) -> bool:
        """Check if a single symlink points to the given CEFS image.

        Args:
            symlink_path: Path to check
            filename_stem: The filename stem (hash + suffix) of the CEFS image

        Returns:
            True if symlink exists and points to this image
        """
        if symlink_path.is_symlink():
            try:
                target = symlink_path.readlink()
                if str(target).startswith(str(self.mount_point) + "/"):
                    # Extract the hash/filename from the symlink target
                    # Format: {mount_point}/XX/HASH_suffix or {mount_point}/XX/HASH_suffix/subdir
                    target_path = Path(target)
                    mount_parts = self.mount_point.parts
                    target_parts = target_path.parts
                    if len(target_parts) >= len(mount_parts) + 2:
                        # The filename part is at the position after mount_point + XX
                        target_filename = target_parts[len(mount_parts) + 1]
                        # Check if this matches our image's filename stem
                        if target_filename == filename_stem:
                            _LOGGER.debug("Found valid symlink: %s -> %s", symlink_path, target)
                            return True
            except OSError as e:
                _LOGGER.error(
                    "Could not read symlink %s: %s - assuming it references the image to be safe",
                    symlink_path,
                    e,
                )
                return True  # When in doubt, keep the image
        return False

    def is_image_referenced(self, filename_stem: str) -> bool:
        """Check if an image is referenced by any symlink.

        Args:
            filename_stem: The image filename stem

        Returns:
            True if any symlink references this image

        Raises:
            ValueError: If image has no manifest data (shouldn't happen for valid images)
        """
        if filename_stem not in self.image_references:
            # This is an error - all valid images should have manifest data
            raise ValueError(f"Image {filename_stem} has no manifest data - this should not happen")

        for dest_path in self.image_references[filename_stem]:
            if self._check_symlink_points_to_image(dest_path, filename_stem):
                return True
        return False

    def find_unreferenced_images(self) -> list[Path]:
        """Find all CEFS images that are not referenced by any symlink.

        Returns:
            List of Path objects for unreferenced CEFS images
        """
        unreferenced = []
        for filename_stem, image_path in self.all_cefs_images.items():
            if filename_stem not in self.referenced_images:
                unreferenced.append(image_path)
        return unreferenced

    def get_summary(self) -> GCSummary:
        """Get summary statistics for reporting.

        Returns:
            GCSummary with statistics
        """
        unreferenced_images = self.find_unreferenced_images()
        space_to_reclaim = 0

        for image_path in unreferenced_images:
            try:
                space_to_reclaim += image_path.stat().st_size
            except OSError:
                _LOGGER.warning("Could not stat unreferenced image: %s", image_path)

        return GCSummary(
            total_images=len(self.all_cefs_images),
            referenced_images=len(self.referenced_images),
            unreferenced_images=len(unreferenced_images),
            space_to_reclaim=space_to_reclaim,
        )

    def get_usage_stats(self) -> ImageUsageStats:
        """Get detailed usage statistics for all CEFS images.

        Returns:
            ImageUsageStats with detailed usage breakdown
        """
        return get_consolidated_image_usage_stats(self)


def get_extraction_path_from_symlink(symlink_target: Path, mount_point: Path) -> Path:
    """Determine what to extract from a CEFS image based on symlink target.

    Returns the relative path after {mount_point}/XX/HASH/ or Path(".") if at root.

    Args:
        symlink_target: The symlink target path
        mount_point: CEFS mount point (e.g., /cefs)

    Examples (assuming mount_point=/cefs):
        /cefs/ab/abcd1234567890abcdef12/content → Path("content")
        /cefs/ab/abcd1234567890abcdef12 → Path(".")
        /cefs/ab/abcd1234567890abcdef12/gcc-4.5 → Path("gcc-4.5")
        /cefs/ab/abcd1234567890abcdef12/libs/boost → Path("libs/boost")
    """
    parts = symlink_target.parts
    mount_parts = mount_point.parts
    # Need at least mount_point + XX + HASH to have any relative path
    if len(parts) <= len(mount_parts) + 2:
        return Path(".")

    relative_parts = parts[len(mount_parts) + 2 :]
    return Path(*relative_parts)


@dataclass(frozen=True)
class ImageAgeFilterResult:
    """Result of filtering images by age."""

    old_enough: list[Path]
    too_recent: list[tuple[Path, datetime.timedelta]]


@dataclass(frozen=True)
class ImageDeletionResult:
    """Result of deleting a CEFS image with its manifest."""

    success: bool
    deleted_size: int
    errors: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class GCSummary:
    """Summary statistics for garbage collection."""

    total_images: int
    referenced_images: int
    unreferenced_images: int
    space_to_reclaim: int


def filter_images_by_age(
    images: list[Path], min_age_delta: datetime.timedelta, now: datetime.datetime
) -> ImageAgeFilterResult:
    """Filter images by age, separating old enough from too recent.

    Args:
        images: List of image paths to filter
        min_age_delta: Minimum age for deletion
        now: Current time to use for age calculation

    Returns:
        ImageAgeFilterResult with old_enough and too_recent lists
    """
    old_enough = []
    too_recent = []

    for image_path in images:
        try:
            mtime = datetime.datetime.fromtimestamp(image_path.stat().st_mtime)
            age = now - mtime
            if age >= min_age_delta:
                old_enough.append(image_path)
            else:
                too_recent.append((image_path, age))
        except OSError:
            # If we can't stat it, include it as potentially broken
            old_enough.append(image_path)

    return ImageAgeFilterResult(old_enough=old_enough, too_recent=too_recent)


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


def delete_image_with_manifest(image_path: Path) -> ImageDeletionResult:
    """Delete a CEFS image and its associated manifest file.

    Args:
        image_path: Path to the CEFS image to delete

    Returns:
        ImageDeletionResult with success status, size, and any errors
    """
    errors = []
    deleted_size = 0

    # Get size before deletion
    try:
        deleted_size = image_path.stat().st_size
    except OSError as e:
        errors.append(f"Could not stat {image_path}: {e}")
        # Try to delete anyway

    # Delete the image
    try:
        image_path.unlink()
    except OSError as e:
        errors.append(f"Failed to delete {image_path}: {e}")
        return ImageDeletionResult(success=False, deleted_size=0, errors=errors)

    # Delete the manifest if it exists
    manifest_path = image_path.with_suffix(".yaml")
    if manifest_path.exists():
        try:
            manifest_path.unlink()
        except OSError as e:
            errors.append(f"Failed to delete manifest {manifest_path}: {e}")
            # This is non-fatal - image was deleted

    return ImageDeletionResult(success=True, deleted_size=deleted_size, errors=errors)


def normalize_dest_path(dest_path: Path, nfs_dir: Path) -> Path:
    """Normalize a destination path to be relative to the NFS directory.

    Converts absolute paths like /opt/gcc to be relative to nfs_dir.
    For example, /opt/gcc becomes nfs_dir/opt/gcc.

    Args:
        dest_path: The destination path (may be absolute or relative)
        nfs_dir: Base NFS directory

    Returns:
        Path object relative to nfs_dir
    """
    if dest_path.is_absolute():
        # Strip leading slash to make it relative
        relative_path = Path(str(dest_path).lstrip("/"))
        return nfs_dir / relative_path
    return nfs_dir / dest_path


def is_consolidated_image(image_path: Path) -> bool:
    """Check if a CEFS image is a consolidated image.

    Consolidated images have 'consolidated' in their filename or contain
    multiple subdirectories when mounted.

    Args:
        image_path: Path to the CEFS image

    Returns:
        True if this is a consolidated image, False otherwise
    """
    # Check filename pattern first (fast)
    if "_consolidated" in image_path.name:
        return True

    # Check manifest for multiple contents (also fast)
    try:
        manifest = read_manifest_from_alongside(image_path)
        if manifest and "contents" in manifest:
            return len(manifest["contents"]) > 1
    except (OSError, yaml.YAMLError):
        pass

    return False


def calculate_image_usage(
    image_path: Path, image_references: dict[str, list[Path]], nfs_dir: Path, mount_point: Path
) -> float:
    """Calculate usage percentage for a CEFS image.

    For individual images: 100% if referenced, 0% if not
    For consolidated images: percentage of subdirectories still referenced

    Args:
        image_path: Path to the CEFS image
        image_references: Dict mapping image stems to expected destinations
        nfs_dir: Base NFS directory

    Returns:
        Usage percentage (0.0 to 100.0)
    """
    filename_stem = image_path.stem

    # Get expected destinations from image_references
    expected_destinations = image_references.get(filename_stem, [])
    if not expected_destinations:
        return 0.0

    # For individual images (single destination), it's binary
    if len(expected_destinations) == 1:
        dest_path = expected_destinations[0]
        # Use the path directly - it's already an absolute path from the manifest
        full_path = Path(dest_path)

        # Check if either main or .bak symlink points to this image
        main_ref = check_if_symlink_references_image(full_path, filename_stem, mount_point)
        bak_ref = check_if_symlink_references_image(
            full_path.with_name(full_path.name + ".bak"), filename_stem, mount_point
        )
        if main_ref or bak_ref:
            return 100.0
        return 0.0

    # For consolidated images, check each subdirectory
    referenced_count = 0
    for dest_path in expected_destinations:
        # Use the path directly - it's already an absolute path from the manifest
        full_path = Path(dest_path)

        # Check if either main or .bak symlink points to this image
        main_ref = check_if_symlink_references_image(full_path, filename_stem, mount_point)
        bak_ref = check_if_symlink_references_image(
            full_path.with_name(full_path.name + ".bak"), filename_stem, mount_point
        )
        if main_ref or bak_ref:
            referenced_count += 1

    usage_percentage = (referenced_count / len(expected_destinations)) * 100.0
    return usage_percentage


def check_if_symlink_references_image(symlink_path: Path, image_stem: str, mount_point: Path) -> bool:
    if not symlink_path.is_symlink():
        return False

    try:
        target = symlink_path.readlink()
        if target.is_absolute() and target.is_relative_to(mount_point):
            mount_parts_len = len(mount_point.parts)
            parts = target.parts
            if len(parts) >= mount_parts_len + 2:
                # The directory name is at index mount_parts_len + 1
                # e.g., for /cefs/0d/0d163f7f3ee984e50fd7d14f_consolidated/subdir
                # parts[mount_parts_len + 1] is "0d163f7f3ee984e50fd7d14f_consolidated"
                target_dir = parts[mount_parts_len + 1]
                return target_dir == image_stem
    except (OSError, IndexError):
        pass

    return False


@dataclass
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


def get_current_symlink_target(dest_path: Path, nfs_dir: Path) -> Path | None:
    """Get the current target of a symlink if it exists.

    Args:
        dest_path: The destination path to check
        nfs_dir: Base NFS directory

    Returns:
        The symlink target Path, or None if not a symlink
    """
    full_path = normalize_dest_path(dest_path, nfs_dir)

    if full_path.is_symlink():
        try:
            return full_path.readlink()
        except OSError:
            pass

    # Also check .bak
    bak_path = full_path.with_name(full_path.name + ".bak")
    if bak_path.is_symlink():
        try:
            return bak_path.readlink()
        except OSError:
            pass

    return None


def get_consolidated_image_usage_stats(
    state: CEFSState,
) -> ImageUsageStats:
    """Calculate detailed usage statistics for CEFS images.

    Args:
        state: CEFSState object with image information

    Returns:
        ImageUsageStats with detailed breakdown
    """
    individual_images = 0
    consolidated_images = 0
    fully_used_consolidated = 0
    partially_used_consolidated = []
    unused_images = []
    total_space = 0
    wasted_space_estimate = 0

    for _filename_stem, image_path in state.all_cefs_images.items():
        try:
            size = image_path.stat().st_size
            total_space += size
        except OSError:
            size = 0

        usage = calculate_image_usage(image_path, state.image_references, state.nfs_dir, state.mount_point)

        if is_consolidated_image(image_path):
            consolidated_images += 1
            if usage == 100.0:
                fully_used_consolidated += 1
            elif usage > 0:
                partially_used_consolidated.append((image_path, usage))
                # Estimate wasted space as the unused portion
                wasted_space_estimate += int(size * (100 - usage) / 100)
            else:
                unused_images.append(image_path)
                wasted_space_estimate += size
        else:
            individual_images += 1
            if usage == 0:
                unused_images.append(image_path)
                wasted_space_estimate += size

    # Sort partially used by usage percentage
    partially_used_consolidated.sort(key=lambda x: x[1])

    return ImageUsageStats(
        total_images=len(state.all_cefs_images),
        individual_images=individual_images,
        consolidated_images=consolidated_images,
        fully_used_consolidated=fully_used_consolidated,
        partially_used_consolidated=partially_used_consolidated,
        unused_images=unused_images,
        total_space=total_space,
        wasted_space_estimate=wasted_space_estimate,
    )
