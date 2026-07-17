"""Cache delta capture utilities for library building.

This module provides utilities to capture only new files added to a cache directory,
enabling efficient packaging of library artifacts without duplicating base runtime files.

The pattern is language-agnostic and can be used for:
- Go: GOCACHE delta (excluding stdlib)
- Python: pip cache delta (excluding base packages)
- JavaScript: npm cache delta (excluding core modules)
"""

from __future__ import annotations

import logging
import shutil
from collections.abc import Callable
from pathlib import Path

_LOGGER = logging.getLogger(__name__)


class CacheDeltaCapture:
    """Captures only new files added to a cache directory after a baseline snapshot.

    This class enables efficient library packaging by:
    1. Recording a baseline of existing cache files (e.g., stdlib)
    2. Running a build operation that adds files to the cache
    3. Extracting only the new files (delta) for packaging

    Example usage:
        delta = CacheDeltaCapture(gocache_dir)
        delta.capture_baseline()      # Record stdlib state
        build_library()               # Adds files to cache
        delta.copy_delta_to(pkg_dir)  # Copy only new files
    """

    def __init__(self, cache_dir: Path):
        """Initialize with the cache directory to monitor.

        Args:
            cache_dir: Path to the cache directory to monitor for changes.
        """
        self.cache_dir = Path(cache_dir)
        self._baseline_files: set[str] | None = None

    @property
    def has_baseline(self) -> bool:
        """Return True if a baseline has been captured."""
        return self._baseline_files is not None

    @property
    def baseline_count(self) -> int:
        """Return number of files in baseline, or 0 if no baseline captured."""
        if self._baseline_files is None:
            return 0
        return len(self._baseline_files)

    def capture_baseline(self) -> int:
        """Record existing files in the cache directory as the baseline.

        Call this before performing operations that add files to the cache.

        Returns:
            Number of files in the baseline.
        """
        self._baseline_files = self._list_files()
        _LOGGER.debug("Captured baseline with %d files from %s", len(self._baseline_files), self.cache_dir)
        return len(self._baseline_files)

    def capture_baseline_from(self, source_dir: Path) -> int:
        """Record files from a different directory as the baseline.

        Useful when the baseline comes from a separate location (e.g., stdlib cache
        stored separately from build cache).

        Args:
            source_dir: Path to directory containing baseline files.

        Returns:
            Number of files in the baseline.
        """
        self._baseline_files = self._list_files_in(source_dir)
        _LOGGER.debug("Captured baseline with %d files from %s", len(self._baseline_files), source_dir)
        return len(self._baseline_files)

    def get_delta(self) -> set[str]:
        """Return relative paths of files added since the baseline.

        Returns:
            Set of relative file paths that are new since baseline.

        Raises:
            RuntimeError: If no baseline has been captured.
        """
        if self._baseline_files is None:
            raise RuntimeError("No baseline captured. Call capture_baseline() first.")

        current_files = self._list_files()
        delta = current_files - self._baseline_files
        _LOGGER.debug("Delta contains %d new files", len(delta))
        return delta

    def get_delta_count(self) -> int:
        """Return number of new files since baseline.

        Returns:
            Count of new files.

        Raises:
            RuntimeError: If no baseline has been captured.
        """
        return len(self.get_delta())

    def get_delta_size_bytes(self) -> int:
        """Return total size in bytes of delta files.

        Returns:
            Total size of new files in bytes.

        Raises:
            RuntimeError: If no baseline has been captured.
        """
        total = 0
        for rel_path in self.get_delta():
            file_path = self.cache_dir / rel_path
            if file_path.exists():
                total += file_path.stat().st_size
        return total

    def copy_delta_to(self, dest: Path, dry_run: bool = False) -> int:
        """Copy only delta files to destination directory.

        Args:
            dest: Destination directory for delta files.
            dry_run: If True, only log what would be copied without actually copying.

        Returns:
            Number of files copied (or that would be copied in dry_run mode).

        Raises:
            RuntimeError: If no baseline has been captured.
        """
        delta = self.get_delta()

        if dry_run:
            _LOGGER.info("DRY RUN: Would copy %d files to %s", len(delta), dest)
            return len(delta)

        copied = 0
        for rel_path in delta:
            src = self.cache_dir / rel_path
            dst = dest / rel_path

            if not src.exists():
                _LOGGER.warning("Delta file no longer exists: %s", src)
                continue

            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            copied += 1

        _LOGGER.info("Copied %d delta files to %s", copied, dest)
        return copied

    def _list_files(self) -> set[str]:
        """List all files in cache_dir as relative paths."""
        return self._list_files_in(self.cache_dir)

    def _list_files_in(self, directory: Path) -> set[str]:
        """List all files in a directory as relative paths."""
        if not directory.exists():
            return set()
        return {str(f.relative_to(directory)) for f in directory.rglob("*") if f.is_file()}


def copy_and_capture_delta(
    source_cache: Path,
    build_cache: Path,
    build_operation: Callable[[], None],
    delta_dest: Path,
    dry_run: bool = False,
) -> tuple[int, int]:
    """Convenience function to copy baseline, run build, and capture delta.

    This is the common pattern for library building:
    1. Copy existing cache (e.g., stdlib) to build location
    2. Run build operation that adds to cache
    3. Copy only new files to destination

    Args:
        source_cache: Source cache directory (e.g., stdlib cache).
        build_cache: Build cache directory where operation will write.
        build_operation: Callable that performs the build (takes no args).
        delta_dest: Destination for delta files.
        dry_run: If True, skip actual copy operations.

    Returns:
        Tuple of (baseline_count, delta_count).

    Example:
        baseline, delta = copy_and_capture_delta(
            source_cache=stdlib_cache,
            build_cache=temp_cache,
            build_operation=lambda: build_go_library(module, temp_cache),
            delta_dest=package_dir / "cache_delta",
        )
    """
    # Create build cache directory (needed even in dry_run for build_operation)
    build_cache.mkdir(parents=True, exist_ok=True)

    # Copy source cache to build location (skip in dry_run)
    if not dry_run and source_cache.exists():
        shutil.copytree(source_cache, build_cache, dirs_exist_ok=True)

    # Capture baseline from build cache (after copy)
    capture = CacheDeltaCapture(build_cache)
    baseline_count = capture.capture_baseline()

    # Run the build operation
    build_operation()

    # Copy delta to destination
    delta_count = capture.copy_delta_to(delta_dest, dry_run=dry_run)

    return baseline_count, delta_count
