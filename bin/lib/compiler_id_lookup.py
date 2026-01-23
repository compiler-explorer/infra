"""Lookup compiler IDs from installation paths using CE properties files."""

from __future__ import annotations

import logging
import re
import urllib.parse
from collections import defaultdict
from typing import Any

import requests

_LOGGER = logging.getLogger(__name__)

# All languages that have compilers in CE
COMPILER_LANGUAGES = [
    "ada",
    "assembly",
    "c",
    "c++",
    "circle",
    "circt",
    "clean",
    "cpp_for_opencl",
    "cppx",
    "cppx_blue",
    "cppx_gold",
    "d",
    "dart",
    "fortran",
    "go",
    "hlsl",
    "ispc",
    "javascript",
    "mlir",
    "nim",
    "objc",
    "objc++",
    "pony",
    "racket",
    "rust",
    "swift",
    "zig",
]


class CompilerIdLookup:
    """Looks up compiler IDs from executable paths using CE properties files."""

    def __init__(self):
        self._exe_to_ids: dict[str, set[str]] = defaultdict(set)
        self._loaded = False

    def _load_properties_for_language(self, language: str) -> dict[str, dict[str, Any]]:
        """Load compiler properties for a single language from GitHub."""
        encoded_language = urllib.parse.quote(language)
        url = f"https://raw.githubusercontent.com/compiler-explorer/compiler-explorer/main/etc/config/{encoded_language}.amazon.properties"

        try:
            request = requests.get(url, timeout=30)
            if not request.ok:
                _LOGGER.debug("Could not fetch properties for %s: %s", language, request.status_code)
                return {}
        except requests.RequestException as e:
            _LOGGER.debug("Error fetching properties for %s: %s", language, e)
            return {}

        compilers: dict[str, dict[str, Any]] = defaultdict(dict)
        pattern = re.compile(r"^compiler\.([^.]+)\.(\w+)=(.*)$")

        for line in request.text.splitlines():
            match = pattern.match(line)
            if match:
                compiler_id = match.group(1)
                prop_name = match.group(2)
                prop_value = match.group(3)
                compilers[compiler_id][prop_name] = prop_value

        return compilers

    def _load_all_properties(self) -> None:
        """Load properties for all languages and build exe-to-id mapping."""
        if self._loaded:
            return

        _LOGGER.debug("Loading compiler properties from CE repository...")
        for language in COMPILER_LANGUAGES:
            compilers = self._load_properties_for_language(language)
            for compiler_id, props in compilers.items():
                if "exe" in props:
                    exe_path = props["exe"]
                    self._exe_to_ids[exe_path].add(compiler_id)

        self._loaded = True
        _LOGGER.debug("Loaded %d unique exe paths", len(self._exe_to_ids))

    def get_compiler_ids(self, exe_path: str) -> set[str]:
        """Get compiler IDs for a given executable path.

        Args:
            exe_path: Full path to the compiler executable (e.g., /opt/compiler-explorer/gcc-14.2.0/bin/g++)

        Returns:
            Set of compiler IDs that use this executable
        """
        self._load_all_properties()
        return self._exe_to_ids.get(exe_path, set())

    def get_all_mappings(self) -> dict[str, set[str]]:
        """Get all exe path to compiler ID mappings.

        Returns:
            Dictionary mapping exe paths to sets of compiler IDs
        """
        self._load_all_properties()
        return dict(self._exe_to_ids)


# Module-level singleton for efficiency
_lookup_instance: CompilerIdLookup | None = None


def get_compiler_ids_for_exe(exe_path: str) -> set[str]:
    """Get compiler IDs for a given executable path.

    This uses a module-level singleton to avoid reloading properties multiple times.

    Args:
        exe_path: Full path to the compiler executable

    Returns:
        Set of compiler IDs that use this executable
    """
    global _lookup_instance
    if _lookup_instance is None:
        _lookup_instance = CompilerIdLookup()
    return _lookup_instance.get_compiler_ids(exe_path)


def get_compiler_id_lookup() -> CompilerIdLookup:
    """Get the singleton CompilerIdLookup instance.

    Returns:
        The CompilerIdLookup instance
    """
    global _lookup_instance
    if _lookup_instance is None:
        _lookup_instance = CompilerIdLookup()
    return _lookup_instance
