"""Go compiler installable with automatic stdlib cache building."""

from __future__ import annotations

import logging
import subprocess
from typing import Any

from lib.golang_stdlib import DEFAULT_ARCHITECTURES, STDLIB_CACHE_DIR, build_go_stdlib
from lib.installable.archives import TarballInstallable
from lib.installation_context import InstallationContext
from lib.staging import StagingDir

_LOGGER = logging.getLogger(__name__)


class GoInstallable(TarballInstallable):
    """Go compiler installable that automatically builds stdlib cache during staging.

    This extends TarballInstallable to add automatic Go standard library cache building
    during the staging phase. The stdlib cache is built for configured architectures
    and stored in the installation directory before it's moved to the final destination.
    """

    def __init__(self, install_context: InstallationContext, config: dict[str, Any]):
        super().__init__(install_context, config)
        # Get architectures from config, or use defaults
        self.build_stdlib_archs = self.config_get("build_stdlib_archs", DEFAULT_ARCHITECTURES)
        # Allow disabling stdlib build with config option
        self.build_stdlib = self.config_get("build_stdlib", True)

    def stage(self, staging: StagingDir) -> None:
        """Stage the Go installation and build stdlib cache.

        This method:
        1. Calls parent stage() to extract and setup the Go installation
        2. Builds the Go standard library cache for configured architectures
        3. Stores the cache in <staging-dir>/<install-path>/cache
        """
        # First, do the normal tarball extraction and setup
        super().stage(staging)

        # Skip stdlib build if disabled in config
        if not self.build_stdlib:
            self._logger.info("Stdlib building disabled for %s", self.name)
            return

        # The Go installation is now in staging.path / self.untar_path
        go_install_dir = staging.path / self.untar_path

        if not go_install_dir.exists():
            raise RuntimeError(f"Go installation directory not found at {go_install_dir}")

        # Build the stdlib cache
        self._logger.info("Building Go stdlib cache for %s", self.name)
        self._logger.info("  Architectures: %s", ", ".join(self.build_stdlib_archs))

        # Use a cache directory inside the Go installation
        cache_dir = go_install_dir / STDLIB_CACHE_DIR

        try:
            success = build_go_stdlib(
                go_installation_path=go_install_dir,
                architectures=self.build_stdlib_archs,
                cache_dir=cache_dir,
                dry_run=self.install_context.dry_run,
            )

            if success:
                self._logger.info("✓ Successfully built stdlib cache for %s", self.name)
            else:
                self._logger.warning("Failed to build stdlib cache for %s", self.name)
                # Don't fail the installation, just warn
                # The Go compiler will still work, just slower on first use

        except (RuntimeError, OSError, subprocess.SubprocessError) as e:
            self._logger.error("Error building stdlib cache for %s: %s", self.name, e)
            # Don't fail the installation, just warn
            # The Go compiler will still work, just slower on first use

    def __repr__(self) -> str:
        return f"GoInstallable({self.name}, {self.install_path})"
