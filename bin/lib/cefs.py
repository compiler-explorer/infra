#!/usr/bin/env python3
"""CEFS (Compiler Explorer FileSystem) v2 utility functions."""

from __future__ import annotations

import hashlib
import logging
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lib.installable.installable import Installable
import humanfriendly

from .cefs_manifest import generate_cefs_filename, write_manifest_alongside_image
from .config import SquashfsConfig
from .squashfs import create_squashfs_image, extract_squashfs_image

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class CEFSPaths:
    """Container for CEFS image path and mount path."""

    image_path: Path
    mount_path: Path


def get_cefs_image_path(image_dir: Path, filename: Path) -> Path:
    """Get the full CEFS image path for a given filename.

    Args:
        image_dir: Base image directory (e.g., Path("/efs/cefs-images"))
        filename: Complete filename with descriptive suffix

    Returns:
        Full path to the CEFS image file (e.g., /efs/cefs-images/a1/a1b2c3d4....sqfs)
    """
    return image_dir / str(filename)[:2] / filename


def get_cefs_mount_path(mount_point: Path, filename: Path) -> Path:
    """Get the full CEFS mount target path for a given hash.

    Args:
        mount_point: Base mount point (e.g., Path("/cefs"))
        filename: Complete filename with descriptive suffix

    Returns:
        Full path to the CEFS mount target (e.g., /cefs/a1/a1b2c3d4...)
    """
    return mount_point / str(filename)[:2] / filename.with_suffix("")


def get_cefs_paths(image_dir: Path, mount_point: Path, filename: Path) -> CEFSPaths:
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


def get_cefs_filename_for_image(squashfs_path: Path, operation: str, path: Path | None = None) -> Path:
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

    # Create uniquely named temp file in same directory for atomic rename
    with tempfile.NamedTemporaryFile(
        dir=cefs_image_path.parent, suffix=".tmp", prefix="cefs_", delete=False
    ) as temp_file:
        temp_path = Path(temp_file.name)
        with open(source_path, "rb") as source_file:
            shutil.copyfileobj(source_file, temp_file, length=1024 * 1024)
    try:
        # Atomic rename - only complete files get .sqfs extension
        temp_path.replace(cefs_image_path)
    except Exception:
        # Clean up temp file on any failure
        temp_path.unlink(missing_ok=True)
        raise


def deploy_to_cefs_with_manifest(source_path: Path, cefs_image_path: Path, manifest: dict) -> None:
    """Deploy an image to CEFS with its manifest.

    Atomically copies the squashfs image and writes its manifest alongside.

    Args:
        source_path: Source squashfs image to deploy
        cefs_image_path: Target path in CEFS images directory
        manifest: Manifest dictionary to write alongside the image

    Raises:
        Exception: If deployment fails (all files are cleaned up)
    """
    copy_to_cefs_atomically(source_path, cefs_image_path)
    write_manifest_alongside_image(manifest, cefs_image_path)


def backup_and_symlink(nfs_path: Path, cefs_target: Path, dry_run: bool, defer_cleanup: bool) -> None:
    """Backup NFS directory and create CEFS symlink with rollback on failure.

    Args:
        nfs_path: Path to the NFS directory to backup and replace with symlink
        cefs_target: Target path for the CEFS symlink
        dry_run: If True, only log what would be done
        defer_cleanup: If True, rename old .bak to .DELETE_ME_<timestamp> instead of deleting
    """
    import datetime

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
        return available_bytes >= required_bytes
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


def create_consolidated_image(
    squashfs_config: SquashfsConfig,
    items: list[tuple[Path, Path, str, Path]],
    temp_dir: Path,
    output_path: Path,
) -> None:
    """Create a consolidated squashfs image from multiple CEFS items.

    Args:
        squashfs_config: SquashFsConfig object with tool paths and settings
        items: List of (nfs_path, squashfs_path, subdirectory_name, extraction_path) tuples
        temp_dir: Temporary directory for extraction
        output_path: Path for the consolidated squashfs image

    Raises:
        RuntimeError: If consolidation fails
    """
    extraction_dir = temp_dir / "extract"
    extraction_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Extract each squashfs image to its subdirectory
        total_compressed_size = 0
        total_extracted_size = 0

        for _nfs_path, squashfs_path, subdir_name, extraction_path in items:
            subdir_path = extraction_dir / subdir_name
            compressed_size = squashfs_path.stat().st_size
            total_compressed_size += compressed_size

            _LOGGER.info(
                "Extracting %s (%s) from %s to %s",
                squashfs_path,
                humanfriendly.format_size(compressed_size, binary=True),
                extraction_path,
                subdir_path,
            )

            extract_squashfs_image(squashfs_config, squashfs_path, subdir_path, extraction_path)

            # Measure extracted size and calculate compression ratio
            extracted_size = get_directory_size(subdir_path)
            total_extracted_size += extracted_size
            compression_ratio = extracted_size / compressed_size if compressed_size > 0 else 0

            _LOGGER.info(
                "Extracted %s -> %s (%.1fx compression)",
                humanfriendly.format_size(compressed_size, binary=True),
                humanfriendly.format_size(extracted_size, binary=True),
                compression_ratio,
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
    consolidated_filename: Path,
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
        # New target: /cefs/XX/HASH_consolidated/subdir_name
        new_target = get_cefs_mount_path(mount_point, consolidated_filename) / subdir_name

        try:
            backup_and_symlink(symlink_path, new_target, dry_run=False, defer_cleanup=defer_cleanup)
            _LOGGER.info("Updated symlink %s -> %s", symlink_path, new_target)
        except RuntimeError as e:
            raise RuntimeError(f"Failed to update symlink {symlink_path}: {e}") from e


def parse_cefs_target(cefs_target: Path, cefs_image_dir: Path) -> tuple[Path, bool]:
    """Parse CEFS symlink target and return image path and consolidation status.

    Args:
        cefs_target: The symlink target (e.g., /cefs/XX/HASH or /cefs/XX/HASH/subdir)
        cefs_image_dir: Base directory for CEFS images (e.g., /efs/cefs-images)

    Returns:
        Tuple of (cefs_image_path, is_already_consolidated)

    Raises:
        ValueError: If the CEFS target format is invalid

    Examples:
        >>> parse_cefs_target(Path("/cefs/9d/9da642f654bc890a12345678"), Path("/efs/cefs-images"))
        (Path("/efs/cefs-images/9d/9da642f654bc890a12345678_gcc.sqfs"), False)

        >>> parse_cefs_target(Path("/cefs/ab/abcdef1234567890abcdef12/gcc-4.5"), Path("/efs/cefs-images"))
        (Path("/efs/cefs-images/ab/abcdef1234567890abcdef12_consolidated.sqfs"), True)
    """
    parts = cefs_target.parts
    # Expected: ('', 'cefs', 'XX', 'HASH', ...) for /cefs/XX/HASH/...

    if len(parts) < 4:  # Need at least '', 'cefs', 'XX', 'HASH'
        raise ValueError(f"Invalid CEFS target format: {cefs_target}")

    if parts[1] != "cefs":
        raise ValueError(f"CEFS target must start with /cefs: {cefs_target}")

    hash_prefix = parts[2]  # XX
    hash = parts[3]  # 24-char hash

    image_dir_subdir = cefs_image_dir / hash_prefix
    matching_files = list(image_dir_subdir.glob(f"{hash}*.sqfs"))

    if not matching_files:
        raise ValueError(f"No CEFS image found for hash {hash} in {image_dir_subdir}")

    cefs_image_path = matching_files[0]

    # If there are more parts after the hash, it's already consolidated
    is_already_consolidated = len(parts) > 4

    return cefs_image_path, is_already_consolidated


def describe_cefs_image(hash_value: str, cefs_mount_point: Path = Path("/cefs")) -> list[str]:
    """Get top-level entries from a CEFS image by triggering autofs mount.

    Args:
        hash_value: The CEFS hash to describe
        cefs_mount_point: Base CEFS mount point (default: /cefs)

    Returns:
        List of top-level entry names in the CEFS image
    """
    cefs_path = get_cefs_mount_path(cefs_mount_point, Path(hash_value))
    try:
        # This will trigger autofs mount
        entries = list(cefs_path.iterdir())
        return [entry.name for entry in entries]
    except OSError as e:
        _LOGGER.warning("Could not list contents of %s: %s", cefs_path, e)
        return []


class CEFSState:
    """Track CEFS images and their references for garbage collection using manifests."""

    def __init__(self, nfs_dir: Path, cefs_image_dir: Path):
        """Initialize CEFS state tracker.

        Args:
            nfs_dir: Base NFS directory (e.g., /opt/compiler-explorer)
            cefs_image_dir: CEFS images directory (e.g., /efs/cefs-images)
        """
        self.nfs_dir = nfs_dir
        self.cefs_image_dir = cefs_image_dir
        self.all_cefs_images: dict[str, Path] = {}  # filename_stem -> image_path
        self.image_references: dict[str, list[Path]] = {}  # filename_stem -> list of expected symlink destinations
        self.referenced_images: set[str] = set()  # Set of filename_stems that have valid symlinks

    def scan_cefs_images_with_manifests(self) -> None:
        """Scan all CEFS images and read their manifests to determine expected references."""
        from .cefs_manifest import read_manifest_from_alongside

        if not self.cefs_image_dir.exists():
            _LOGGER.warning("CEFS images directory does not exist: %s", self.cefs_image_dir)
            return

        for subdir in self.cefs_image_dir.iterdir():
            if subdir.is_dir():
                for image_file in subdir.glob("*.sqfs"):
                    # Store by filename stem (includes hash and suffix)
                    filename_stem = image_file.stem
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
                            # No manifest or no contents - fallback to old-style checking
                            self.image_references[filename_stem] = []
                            _LOGGER.debug("No manifest for %s, will check with fallback", filename_stem)
                    except Exception as e:
                        _LOGGER.warning("Failed to read manifest for %s: %s", image_file, e)
                        self.image_references[filename_stem] = []

    def check_symlink_references(self) -> None:
        """Check if expected symlinks exist and point to the correct CEFS images."""
        for filename_stem, expected_destinations in self.image_references.items():
            # For images with manifests, check if symlinks exist at expected destinations
            if expected_destinations:
                for dest_path in expected_destinations:
                    if self._check_symlink_points_to_image(dest_path, filename_stem):
                        self.referenced_images.add(filename_stem)
                        break  # At least one valid reference found
            else:
                # Fallback: scan for any symlinks pointing to this image (for older images without manifests)
                if self._find_any_symlink_to_image(filename_stem):
                    self.referenced_images.add(filename_stem)

    def _check_symlink_points_to_image(self, dest_path: Path, filename_stem: str) -> bool:
        """Check if a symlink at dest_path points to the given CEFS image.

        Args:
            dest_path: Expected destination path for symlink
            filename_stem: The filename stem (hash + suffix) of the CEFS image

        Returns:
            True if symlink exists and points to this image
        """
        full_path = dest_path if dest_path.is_absolute() else self.nfs_dir / dest_path.relative_to(Path("/"))

        if full_path.is_symlink():
            try:
                target = full_path.readlink()
                if str(target).startswith("/cefs/"):
                    # Extract the hash/filename from the symlink target
                    # Format: /cefs/XX/HASH_suffix or /cefs/XX/HASH_suffix/subdir
                    parts = str(target).split("/")
                    if len(parts) >= 4:
                        # The filename part is at index 3
                        target_filename = parts[3]
                        # Check if this matches our image's filename stem
                        if target_filename == filename_stem:
                            _LOGGER.debug("Found valid symlink: %s -> %s", full_path, target)
                            return True
            except OSError as e:
                _LOGGER.debug("Could not read symlink %s: %s", full_path, e)
        return False

    def _find_any_symlink_to_image(self, filename_stem: str) -> bool:
        """Fallback method: scan filesystem for any symlink pointing to this image.

        This is used for images without manifests.

        Args:
            filename_stem: The filename stem to search for

        Returns:
            True if any symlink points to this image
        """
        # This is expensive but only used for images without manifests
        # Check common locations first
        for subdir in self.nfs_dir.iterdir():
            if subdir.is_symlink():
                try:
                    target = str(subdir.readlink())
                    if "/cefs/" in target and filename_stem in target:
                        return True
                except OSError:
                    continue

            # Check .bak versions too
            bak_path = subdir.with_name(subdir.name + ".bak")
            if bak_path.is_symlink():
                try:
                    target = str(bak_path.readlink())
                    if "/cefs/" in target and filename_stem in target:
                        return True
                except OSError:
                    continue
        return False

    def scan_installables(self, installables: list[Installable]) -> None:
        """Legacy method kept for compatibility - now just logs a warning.

        The new implementation uses manifests instead of scanning installables.
        """
        _LOGGER.warning("scan_installables called but manifest-based GC doesn't use it")

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

    def get_summary(self) -> dict[str, int]:
        """Get summary statistics for reporting.

        Returns:
            Dictionary with summary statistics
        """
        unreferenced_images = self.find_unreferenced_images()
        space_to_reclaim = 0

        for image_path in unreferenced_images:
            try:
                space_to_reclaim += image_path.stat().st_size
            except OSError:
                _LOGGER.warning("Could not stat unreferenced image: %s", image_path)

        return {
            "total_images": len(self.all_cefs_images),
            "referenced_images": len(self.referenced_images),
            "unreferenced_images": len(unreferenced_images),
            "space_to_reclaim": space_to_reclaim,
        }


def get_extraction_path_from_symlink(symlink_target: Path) -> Path:
    """Determine what to extract from a CEFS image based on symlink target.

    Returns the relative path after /cefs/XX/HASH/ or Path(".") if at root.

    Examples:
        /cefs/ab/abcd1234567890abcdef12/content → Path("content")
        /cefs/ab/abcd1234567890abcdef12 → Path(".")
        /cefs/ab/abcd1234567890abcdef12/gcc-4.5 → Path("gcc-4.5")
        /cefs/ab/abcd1234567890abcdef12/libs/boost → Path("libs/boost")
    """
    parts = symlink_target.parts
    if len(parts) <= 4:
        return Path(".")

    relative_parts = parts[4:]
    return Path(*relative_parts)
