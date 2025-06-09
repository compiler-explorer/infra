#!/usr/bin/env python3

from typing import Dict, Optional, Tuple

from lib.amazon_properties import get_properties_compilers_and_libraries
from lib.compiler_info import CompilerInfo
from lib.library_platform import LibraryPlatform


class CompilerPropertyManager:
    """Manages loading and caching of compiler properties."""

    def __init__(self, logger, platform: LibraryPlatform):
        self.logger = logger
        self.platform = platform
        self._props_cache: Dict[str, Tuple[Dict[str, dict], Dict[str, dict]]] = {}

    def get_compiler_properties(
        self, language: str, force_reload: bool = False
    ) -> Tuple[Dict[str, dict], Dict[str, dict]]:
        """Load and cache compiler properties for a language."""
        cache_key = f"{language}_{self.platform.value}"

        if not force_reload and cache_key in self._props_cache:
            return self._props_cache[cache_key]

        result = get_properties_compilers_and_libraries(language, self.logger, self.platform, True)
        self._props_cache[cache_key] = result

        self.logger.info(f"Loaded {len(result[0])} total compilers for {self.platform.value}")
        return result

    def get_compiler_info(self, language: str, compiler_id: str) -> Optional[CompilerInfo]:
        """Get a CompilerInfo object for a specific compiler."""
        compilers, _ = self.get_compiler_properties(language)

        if compiler_id not in compilers:
            return None

        return CompilerInfo(compiler_id, compilers[compiler_id])

    def get_supported_compilers(self, language: str, platform_filter: bool = True) -> Dict[str, CompilerInfo]:
        """Get all supported compilers for a language, optionally filtered by platform compatibility."""
        compilers, _ = self.get_compiler_properties(language)
        supported = {}

        for compiler_id, props in compilers.items():
            compiler_info = CompilerInfo(compiler_id, props)

            # Check if compiler exists
            if not compiler_info.exists:
                self.logger.debug(f"Skipping {compiler_id}: executable {compiler_info.executable} not found")
                continue

            # Platform-specific filtering
            if platform_filter:
                if self.platform == LibraryPlatform.Windows:
                    # For Windows, support MSVC, MinGW GCC, and MinGW Clang compilers
                    if not compiler_info.is_windows_compiler:
                        continue
                else:
                    # For Linux, support GCC, Clang, and other Unix compilers (exclude Windows compilers)
                    if compiler_info.is_windows_compiler:
                        continue

            supported[compiler_id] = compiler_info

        self.logger.info(f"Found {len(supported)} supported compilers on {self.platform.value}")
        return supported