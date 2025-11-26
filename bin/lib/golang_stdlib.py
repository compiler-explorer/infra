"""Go standard library building utilities.

This module contains the core logic for building Go standard libraries.
It is separate from CLI code to avoid circular import issues.
"""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path

_LOGGER = logging.getLogger(__name__)

DEFAULT_ARCHITECTURES = ["linux/amd64", "linux/arm", "linux/arm64"]
STDLIB_CACHE_DIR = "cache"


def is_go_installation(install_path: Path) -> bool:
    """Check if a path contains a Go installation."""
    go_binary = install_path / "go" / "bin" / "go"
    return go_binary.exists() and go_binary.is_file()


def get_arch_marker_file(cache_dir: Path, arch: str) -> Path:
    """Get the marker file path for a specific architecture.

    Args:
        cache_dir: Path to the cache directory
        arch: Architecture in format "OS/ARCH" (e.g., "linux/amd64")

    Returns:
        Path to the marker file for this architecture
    """
    # Convert "linux/amd64" to ".built_linux_amd64"
    safe_arch = arch.replace("/", "_")
    return cache_dir / f".built_{safe_arch}"


def is_stdlib_already_built(install_path: Path, architectures: list[str] | None = None) -> bool:
    """Check if standard library has already been built for this Go installation.

    Args:
        install_path: Path to the Go installation directory
        architectures: List of architectures to check. If None, uses DEFAULT_ARCHITECTURES

    Returns:
        True if stdlib is already built for all specified architectures, False otherwise
    """
    if architectures is None:
        architectures = DEFAULT_ARCHITECTURES

    cache_dir = install_path / STDLIB_CACHE_DIR

    # Check if cache directory exists and is non-empty
    if not cache_dir.exists() or not any(cache_dir.iterdir()):
        return False

    # Check if all architectures have been built
    for arch in architectures:
        marker_file = get_arch_marker_file(cache_dir, arch)
        if not marker_file.exists():
            _LOGGER.debug("Stdlib not built for %s on %s", install_path, arch)
            return False

    _LOGGER.debug("Stdlib already built for %s (all architectures)", install_path)
    return True


def build_go_stdlib(
    go_installation_path: Path,
    architectures: list[str] | None = None,
    cache_dir: Path | None = None,
    dry_run: bool = False,
) -> bool:
    """Build Go standard library for specified architectures.

    Args:
        go_installation_path: Path to the Go installation (contains go/bin/go)
        architectures: List of GOOS/GOARCH combinations (e.g., ["linux/amd64", "linux/arm64"])
                      If None, uses DEFAULT_ARCHITECTURES
        cache_dir: Custom cache directory path. If None, uses <install-dir>/cache
        dry_run: If True, only show what would be done without executing

    Returns:
        True if build succeeded, False otherwise

    Raises:
        RuntimeError: If Go installation is invalid or build fails
    """
    if architectures is None:
        architectures = DEFAULT_ARCHITECTURES

    go_binary = go_installation_path / "go" / "bin" / "go"
    if not go_binary.exists():
        raise RuntimeError(f"Go binary not found at {go_binary}")

    goroot = go_installation_path / "go"
    gocache = cache_dir if cache_dir is not None else go_installation_path / STDLIB_CACHE_DIR

    # Create cache directory (even in dry-run mode)
    gocache.mkdir(exist_ok=True, parents=True)

    if dry_run:
        _LOGGER.info("DRY RUN: Building stdlib for %s", go_installation_path)
    else:
        _LOGGER.info("Building Go stdlib for %s", go_installation_path.name)

    _LOGGER.info("  GOROOT: %s", goroot)
    _LOGGER.info("  GOCACHE: %s", gocache)

    env = os.environ.copy()
    env["GOROOT"] = str(goroot)
    env["GOCACHE"] = str(gocache)

    success_count = 0
    failed_archs = []

    for arch in architectures:
        try:
            goos, goarch = arch.split("/")
        except ValueError:
            _LOGGER.error("Invalid architecture format '%s', expected 'OS/ARCH' (e.g., 'linux/amd64')", arch)
            failed_archs.append(arch)
            continue

        _LOGGER.info("  Building for %s/%s...", goos, goarch)

        build_env = env.copy()
        build_env["GOOS"] = goos
        build_env["GOARCH"] = goarch

        try:
            result = subprocess.run(
                [str(go_binary), "build", "-v", "std"],
                env=build_env,
                capture_output=True,
                text=True,
                check=False,
                timeout=600,  # 10 minute timeout per architecture
            )

            if result.returncode != 0:
                _LOGGER.error("Failed to build stdlib for %s/%s:", goos, goarch)
                _LOGGER.error("  stdout: %s", result.stdout)
                _LOGGER.error("  stderr: %s", result.stderr)
                failed_archs.append(arch)
            else:
                _LOGGER.info("  ✓ Built for %s/%s", goos, goarch)
                success_count += 1
                # Create marker file for this architecture
                marker_file = get_arch_marker_file(gocache, arch)
                marker_file.write_text(f"Built at: {os.environ.get('USER', 'unknown')}\n")

        except subprocess.TimeoutExpired:
            _LOGGER.error("Timeout building stdlib for %s/%s", goos, goarch)
            failed_archs.append(arch)
        except OSError as e:
            _LOGGER.error("Error building stdlib for %s/%s: %s", goos, goarch, e)
            failed_archs.append(arch)

    if failed_archs:
        _LOGGER.warning("Failed to build for architectures: %s", ", ".join(failed_archs))

    if success_count > 0:
        _LOGGER.info("✓ Successfully built stdlib for %d/%d architectures", success_count, len(architectures))
        return True
    else:
        _LOGGER.error("✗ Failed to build stdlib for all architectures")
        return False
