#!/usr/bin/env python3
"""CEFS state management and analysis."""

from __future__ import annotations

import logging
from pathlib import Path

import humanfriendly
from lib.cefs.consolidation import (
    calculate_image_usage,
    extract_candidates_from_manifest,
    is_consolidated_image,
    should_reconsolidate_image,
)
from lib.cefs.gc import GCSummary
from lib.cefs.models import ConsolidationCandidate, ImageUsageStats
from lib.cefs_manifest import read_manifest_from_alongside

_LOGGER = logging.getLogger(__name__)


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
            if not subdir.is_dir():
                continue

            # First check for .yaml.inprogress files (incomplete operations)
            for inprogress_file in subdir.glob("*.yaml.inprogress"):
                self.inprogress_images.append(inprogress_file)
                _LOGGER.warning("Found in-progress manifest: %s", inprogress_file)

            for image_file in subdir.glob("*.sqfs"):
                filename_stem = image_file.stem

                # SAFETY: Check if this image has an .yaml.inprogress file indicating incomplete operation
                # This prevents deletion of images that are being installed/converted/consolidated
                # even if the operation is taking a long time or has failed partway through
                inprogress_path = Path(str(image_file.with_suffix(".yaml")) + ".inprogress")
                if inprogress_path.exists():
                    _LOGGER.info("Skipping image with in-progress operation: %s", image_file)
                    self.referenced_images.add(filename_stem)
                    continue

                manifest_path = image_file.with_suffix(".yaml")
                if not manifest_path.exists():
                    self.broken_images.append(image_file)
                    _LOGGER.error(
                        "BROKEN IMAGE: %s has no manifest or inprogress marker - needs investigation", image_file
                    )
                    continue

                self.all_cefs_images[filename_stem] = image_file

                try:
                    manifest = read_manifest_from_alongside(image_file)
                except Exception as e:
                    _LOGGER.warning("Failed to read manifest for %s: %s", image_file, e)
                    self.image_references[filename_stem] = []
                    continue

                if manifest and "contents" in manifest:
                    destinations = [
                        Path(content["destination"]) for content in manifest["contents"] if "destination" in content
                    ]
                    self.image_references[filename_stem] = destinations
                    _LOGGER.debug("Image %s expects %d symlinks", filename_stem, len(destinations))
                else:
                    self.image_references[filename_stem] = []
                    _LOGGER.warning("Manifest for %s has no contents", filename_stem)

    def check_symlink_references(self) -> None:
        """Check if expected symlinks exist and point to the correct CEFS images."""
        for filename_stem, expected_destinations in self.image_references.items():
            if not expected_destinations:
                image_path = self.all_cefs_images.get(filename_stem)
                if image_path:
                    self.broken_images.append(image_path)
                    self.referenced_images.add(filename_stem)
                    _LOGGER.error("BROKEN IMAGE: %s has invalid manifest - needs investigation", image_path)
                continue

            for dest_path in expected_destinations:
                if self._check_symlink_points_to_image(dest_path, filename_stem):
                    self.referenced_images.add(filename_stem)
                    break

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
        if not symlink_path.is_symlink():
            return False

        try:
            target = symlink_path.readlink()
        except OSError as e:
            _LOGGER.error(
                "Could not read symlink %s: %s - assuming it references the image to be safe", symlink_path, e
            )
            return True  # When in doubt, keep the image

        if not str(target).startswith(str(self.mount_point) + "/"):
            return False

        # Extract the hash/filename from the symlink target
        # Format: {mount_point}/XX/HASH_suffix or {mount_point}/XX/HASH_suffix/subdir
        target_parts = Path(target).parts
        mount_parts = self.mount_point.parts
        if len(target_parts) < len(mount_parts) + 2:
            return False

        # The filename part is at the position after mount_point + XX
        target_filename = target_parts[len(mount_parts) + 1]
        if target_filename == filename_stem:
            _LOGGER.debug("Found valid symlink: %s -> %s", symlink_path, target)
            return True
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
            raise ValueError(f"Image {filename_stem} has no manifest data - this should not happen")

        return any(
            self._check_symlink_points_to_image(dest_path, filename_stem)
            for dest_path in self.image_references[filename_stem]
        )

    def find_unreferenced_images(self) -> list[Path]:
        """Find all CEFS images that are not referenced by any symlink.

        Returns:
            List of Path objects for unreferenced CEFS images
        """
        return [
            image_path
            for filename_stem, image_path in self.all_cefs_images.items()
            if filename_stem not in self.referenced_images
        ]

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
        individual_images = 0
        consolidated_images = 0
        fully_used_consolidated = 0
        partially_used_consolidated = []
        unused_images = []
        total_space = 0
        wasted_space_estimate = 0

        for _filename_stem, image_path in self.all_cefs_images.items():
            try:
                size = image_path.stat().st_size
                total_space += size
            except OSError:
                size = 0

            usage = calculate_image_usage(image_path, self.image_references, self.mount_point)

            if is_consolidated_image(image_path):
                consolidated_images += 1
                if usage == 100.0:
                    fully_used_consolidated += 1
                elif usage > 0:
                    partially_used_consolidated.append((image_path, usage))
                    wasted_space_estimate += int(size * (100 - usage) / 100)
                else:
                    unused_images.append(image_path)
                    wasted_space_estimate += size
            else:
                individual_images += 1
                if usage == 0:
                    unused_images.append(image_path)
                    wasted_space_estimate += size

        partially_used_consolidated.sort(key=lambda x: x[1])

        return ImageUsageStats(
            total_images=len(self.all_cefs_images),
            individual_images=individual_images,
            consolidated_images=consolidated_images,
            fully_used_consolidated=fully_used_consolidated,
            partially_used_consolidated=partially_used_consolidated,
            unused_images=unused_images,
            total_space=total_space,
            wasted_space_estimate=wasted_space_estimate,
        )

    def _analyze_consolidated_image(self, image_path: Path) -> tuple[float, int] | None:
        """Analyze a consolidated image to get its usage and size.

        Args:
            image_path: Path to the consolidated image

        Returns:
            Tuple of (usage_percentage, size_bytes) or None if analysis fails
        """
        _LOGGER.debug("Checking consolidated image: %s", image_path.name)

        usage = calculate_image_usage(image_path, self.image_references, self.mount_point)

        try:
            size = image_path.stat().st_size
        except OSError:
            return None

        return usage, size

    def _process_image_manifest(self, image_path: Path, size: int, filter_: list[str]) -> list[ConsolidationCandidate]:
        """Process manifest for a consolidated image and extract candidates.

        Args:
            image_path: Path to the consolidated image
            size: Size of the image in bytes
            filter_: Optional filter for selecting items

        Returns:
            List of candidates from this image, or empty list if processing fails
        """
        manifest = read_manifest_from_alongside(image_path)
        if not manifest or "contents" not in manifest:
            _LOGGER.warning("Cannot reconsolidate %s: no manifest", image_path.name)
            return []

        return extract_candidates_from_manifest(manifest, image_path, filter_, size, self.mount_point)

    def gather_reconsolidation_candidates(
        self,
        efficiency_threshold: float,
        max_size_bytes: int,
        undersized_ratio: float,
        filter_: list[str],
    ) -> list[ConsolidationCandidate]:
        """Gather candidates from existing consolidated images for reconsolidation.

        This method analyzes all consolidated images and identifies items that should
        be repacked based on efficiency and size criteria.

        Args:
            efficiency_threshold: Minimum efficiency to keep consolidated image (0.0-1.0)
            max_size_bytes: Maximum size for consolidated images in bytes
            undersized_ratio: Ratio to determine undersized images
            filter_: Optional filter for selecting items

        Returns:
            List of candidate items from consolidated images that should be repacked
        """
        candidates = []

        for image_path in filter(is_consolidated_image, self.all_cefs_images.values()):
            analysis = self._analyze_consolidated_image(image_path)
            if not analysis:
                continue
            usage, size = analysis

            _LOGGER.debug(
                "Image %s: usage=%.1f%%, size=%s (undersized threshold=%s)",
                image_path.name,
                usage,
                humanfriendly.format_size(size, binary=True),
                humanfriendly.format_size(max_size_bytes * undersized_ratio, binary=True),
            )

            should_reconsolidate, reason = should_reconsolidate_image(
                usage=usage,
                size=size,
                efficiency_threshold=efficiency_threshold,
                max_size_bytes=max_size_bytes,
                undersized_ratio=undersized_ratio,
            )

            if not should_reconsolidate:
                _LOGGER.debug("Image %s not marked for reconsolidation", image_path.name)
                continue

            _LOGGER.info("Consolidated image %s marked for reconsolidation: %s", image_path.name, reason)

            image_candidates = self._process_image_manifest(image_path, size, filter_)
            candidates.extend(image_candidates)

        return candidates

    def find_small_consolidated_images(self, size_threshold: int) -> list[Path]:
        """Find consolidated images that are candidates for reconsolidation.

        Args:
            size_threshold: Size threshold in bytes

        Returns:
            List of paths to small consolidated images
        """

        def _is_small_image(im_path: Path) -> bool:
            try:
                return im_path.stat().st_size < size_threshold
            except OSError:
                return False

        return [
            image for image in self.all_cefs_images.values() if is_consolidated_image(image) and _is_small_image(image)
        ]
