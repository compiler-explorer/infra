#!/usr/bin/env python3

from pathlib import Path
from typing import Dict, Optional

from lib.compiler_utils import CMakeCacheExtractor, CompilerPropertyManager, PlatformEnvironmentManager, ScriptExecutor
from lib.library_platform import LibraryPlatform


class CompilerCacheExtractor:
    """Handles CMake cache extraction for compilers."""

    def __init__(
        self,
        logger,
        staging_dir: Optional[str] = None,
        dest: Optional[str] = None,
        platform: Optional[LibraryPlatform] = None,
    ):
        self.logger = logger
        self.platform = platform or LibraryPlatform.Linux
        if self.platform == LibraryPlatform.Windows:
            self.staging_dir = staging_dir or "C:/tmp/staging"
            self.dest = dest or "C:/tmp/staging"
        else:
            self.staging_dir = staging_dir or "/tmp/staging"
            self.dest = dest or "/tmp/staging"

        # Initialize shared utilities
        self.property_manager = CompilerPropertyManager(logger, self.platform)
        self.env_manager = PlatformEnvironmentManager(self.platform)
        self.script_executor = ScriptExecutor(logger, self.platform)
        self.cmake_extractor = CMakeCacheExtractor(logger, self.platform)
        self.compilerprops = None

    def load_compilers(self):
        """Load compiler properties for the specified platform."""
        try:
            compilers, _ = self.property_manager.get_compiler_properties("c++")
            self.compilerprops = compilers
        except Exception as e:
            raise RuntimeError(f"Failed to load compiler properties: {e}") from e

    def get_supported_compilers(self) -> Dict[str, dict]:
        """Get list of supported compilers for the current platform."""
        # Use the shared property manager to get supported compilers
        supported_compilers_info = self.property_manager.get_supported_compilers("c++", platform_filter=True)

        # Convert CompilerInfo objects back to dict format for backward compatibility
        return {compiler_id: info._props for compiler_id, info in supported_compilers_info.items()}

    def get_windows_compilers(self):
        """Get list of Windows MSVC compilers (legacy method for compatibility)."""
        if self.platform != LibraryPlatform.Windows:
            return {}
        return self.get_supported_compilers()

    def setup_compiler_environment(self, compiler_id: str, compiler_props: dict) -> dict:
        """Set up environment variables for a specific compiler."""
        # Get compiler info from the property manager
        compiler_info = self.property_manager.get_compiler_info("c++", compiler_id)
        if not compiler_info:
            # Fallback to creating CompilerInfo from props if not found in manager
            from lib.compiler_utils import CompilerInfo

            compiler_info = CompilerInfo(compiler_id, compiler_props)

        # Use the shared environment manager with default toolchain and arch
        env = self.env_manager.setup_compiler_environment(compiler_info)

        self.logger.debug(f"Environment setup for {compiler_id} ({compiler_info.compiler_type}):")
        self.logger.debug(f"  CC={env.get('CC')}")
        self.logger.debug(f"  CXX={env.get('CXX')}")
        if self.platform == LibraryPlatform.Windows:
            self.logger.debug(f"  INCLUDE={env.get('INCLUDE', 'Not set')}")
            self.logger.debug(f"  LIB={env.get('LIB', 'Not set')}")

        return env

    def extract_cache_for_compiler(self, compiler_id: str, compiler_props: dict, output_dir: Path, upload_to_s3: bool = False) -> bool:
        """Extract CMake cache for a specific compiler using Python implementation."""
        self.logger.info(f"Extracting cache for compiler: {compiler_id}")

        # Get compiler info from the property manager
        compiler_info = self.property_manager.get_compiler_info("c++", compiler_id)
        if not compiler_info:
            # Fallback to creating CompilerInfo from props if not found in manager
            from lib.compiler_utils import CompilerInfo

            compiler_info = CompilerInfo(compiler_id, compiler_props)

        # Create compiler-specific output directory
        compiler_output_dir = output_dir / compiler_id
        compiler_output_dir.mkdir(parents=True, exist_ok=True)

        # Extract C and C++ compiler paths from the compiler info
        cxx_compiler = compiler_info.executable
        c_compiler = compiler_info.get_c_compiler()

        # Get compiler flags
        cxx_flags = compiler_info.options if compiler_info.options else None
        c_flags = cxx_flags  # Use same flags for C as C++ by default

        # Use the Python CMake cache extractor
        success, message = self.cmake_extractor.extract_cache(
            c_compiler_path=c_compiler,
            c_flags=c_flags,
            cxx_compiler_path=cxx_compiler,
            cxx_flags=cxx_flags,
            output_dir=compiler_output_dir,
            create_zip=True,
            keep_temp_dir=False,
            compiler_id=compiler_id,
            upload_to_s3=upload_to_s3,
        )

        if success:
            self.logger.info(f"Successfully extracted cache for {compiler_id}")
            self.logger.debug(message)
            return True
        else:
            self.logger.error(f"Cache extraction failed for {compiler_id}: {message}")
            return False

    def extract_all_compilers(self, output_dir: Path, compiler_filter: Optional[str] = None, upload_to_s3: bool = False):
        """Extract cache files for all or filtered compilers."""
        compilers = self.get_supported_compilers()

        if compiler_filter:
            if compiler_filter not in compilers:
                raise ValueError(f"Compiler '{compiler_filter}' not found. Available: {list(compilers.keys())}")
            compilers = {compiler_filter: compilers[compiler_filter]}

        success_count = 0
        failed_count = 0

        for compiler_id, compiler_props in compilers.items():
            if self.extract_cache_for_compiler(compiler_id, compiler_props, output_dir, upload_to_s3):
                success_count += 1
            else:
                failed_count += 1

        self.logger.info(f"Cache extraction complete: {success_count} succeeded, {failed_count} failed")
        return success_count, failed_count
