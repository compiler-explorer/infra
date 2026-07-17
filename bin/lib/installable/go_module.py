"""Go module installable for library support.

This module provides a minimal installable class for Go modules (libraries).
The actual library building is handled by GoLibraryBuilder, and the compiled
artifacts are distributed via Conan.
"""

from __future__ import annotations

from typing import Any

from lib.installable.installable import Installable
from lib.installation_context import InstallationContext


class GoModuleInstallable(Installable):
    """Installable for Go modules.

    This is a marker class similar to CratesIOInstallable for Rust.
    The actual module sources and compiled cache are built by GoLibraryBuilder
    and distributed via Conan.

    The install path is not used directly - Conan packages are downloaded
    to a separate location and merged into the compilation cache at runtime.
    """

    def __init__(self, install_context: InstallationContext, config: dict[str, Any]):
        super().__init__(install_context, config)
        # Module path (e.g., "github.com/google/uuid")
        self.module_path = self.config_get("module", "")

    def is_installed(self) -> bool:
        """Always returns True - Conan handles the actual installation."""
        return True

    @property
    def is_squashable(self) -> bool:
        """Go modules are not squashable - they're served via Conan."""
        return False

    def __repr__(self) -> str:
        return f"GoModuleInstallable({self.name}, {self.module_path})"
