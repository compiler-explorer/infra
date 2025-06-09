#!/usr/bin/env python3

import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from lib.amazon import S3_STORAGE_BUCKET, s3_client
from lib.compiler_info import CompilerInfo
from lib.library_platform import LibraryPlatform
from lib.platform_environment import PlatformEnvironmentManager


class CMakeCacheExtractor:
    """
    Extracts and packages CMake compiler cache files for reuse across projects.

    This class replicates the functionality of Extract-CMakeCache.ps1 in pure Python,
    providing a cross-platform solution for generating CMake compiler cache files.
    """

    def __init__(self, logger, platform: LibraryPlatform = None):
        self.logger = logger
        self.platform = platform or LibraryPlatform.Linux

    def get_cmake_generator(self, make_utility: str = "make") -> List[str]:
        """
        Get CMake generator arguments based on platform and make utility.

        This follows the same logic as library_builder.py:
        - Windows: Always use Ninja
        - Linux: Use Ninja if make_utility is "ninja"

        Args:
            make_utility: The make utility to use (e.g., "make", "ninja")

        Returns:
            List of CMake arguments for generator selection (empty if default)
        """
        if self.platform == LibraryPlatform.Windows:
            return ["-G", "Ninja"]
        elif self.platform == LibraryPlatform.Linux and make_utility == "ninja":
            return ["-G", "Ninja"]
        return []

    def resolve_compiler_path(self, compiler_path: str) -> Optional[str]:
        """Resolve compiler path to full path."""
        if not compiler_path:
            return None

        try:
            # Try to find the compiler in PATH
            result = shutil.which(compiler_path)
            if result:
                return result

            # If not found, try as absolute path
            if Path(compiler_path).exists():
                return str(Path(compiler_path).resolve())

            raise FileNotFoundError(f"Compiler not found: {compiler_path}")

        except Exception as e:
            self.logger.error(f"Failed to resolve compiler path '{compiler_path}': {e}")
            return None

    def create_minimal_cmake_project(
        self, temp_dir: Path, c_compiler: Optional[str], cxx_compiler: Optional[str]
    ) -> None:
        """Create a minimal CMake project for compiler detection."""
        languages = []
        if c_compiler:
            languages.append("C")
        if cxx_compiler:
            languages.append("CXX")

        languages_str = " ".join(languages)

        # Create CMakeLists.txt
        cmake_content = f"""cmake_minimum_required(VERSION 3.10)
project(CompilerDetection {languages_str})

# Force CMake to detect compiler features and ABI
"""

        # Add language enablement
        for lang in languages:
            cmake_content += f"enable_language({lang})\n"

        # Add test executables
        if c_compiler:
            cmake_content += """
# Create a minimal C executable to ensure full compiler testing
add_executable(test_detection_c test.c)
"""

        if cxx_compiler:
            cmake_content += """
# Create a minimal C++ executable to ensure full compiler testing
add_executable(test_detection_cxx test.cpp)
"""

        # Add information printing
        cmake_content += '\n# Print detected information\nmessage(STATUS "Platform: ${CMAKE_SYSTEM_NAME}")\n'

        if c_compiler:
            cmake_content += """
message(STATUS "C Compiler: ${CMAKE_C_COMPILER}")
message(STATUS "C Compiler ID: ${CMAKE_C_COMPILER_ID}")
message(STATUS "C Compiler Version: ${CMAKE_C_COMPILER_VERSION}")
"""

        if cxx_compiler:
            cmake_content += """
message(STATUS "C++ Compiler: ${CMAKE_CXX_COMPILER}")
message(STATUS "C++ Compiler ID: ${CMAKE_CXX_COMPILER_ID}")
message(STATUS "C++ Compiler Version: ${CMAKE_CXX_COMPILER_VERSION}")
"""

        cmake_content += '\nmessage(STATUS "Cache extraction successful!")\n'

        # Write CMakeLists.txt
        (temp_dir / "CMakeLists.txt").write_text(cmake_content)

        # Create test source files
        if c_compiler:
            c_content = """/* Minimal C test program to verify compiler works */
int main() {
    return 0;
}
"""
            (temp_dir / "test.c").write_text(c_content)

        if cxx_compiler:
            cpp_content = """// Minimal C++ test program to verify compiler works
int main() {
    return 0;
}
"""
            (temp_dir / "test.cpp").write_text(cpp_content)

    def setup_compiler_environment_from_properties(self, compiler_info: CompilerInfo) -> Dict[str, str]:
        """
        Set up compiler environment using the same logic as library_builder.py.
        This ensures MSVC gets proper INCLUDE and LIB paths.
        """
        env_manager = PlatformEnvironmentManager(self.platform)
        return env_manager.setup_compiler_environment(compiler_info)

    def run_cmake_configuration(self, build_dir: Path, env: Dict[str, str]) -> Tuple[bool, str]:
        """Run CMake configuration in the build directory."""
        try:
            self.logger.info("Running CMake to detect compiler...")

            # Use the same generator logic as library_builder.py
            generator_args = self.get_cmake_generator("ninja")  # Default to ninja for cache extraction

            cmd = ["cmake"] + generator_args + [".."]

            if generator_args:
                self.logger.info(f"Using CMake generator: {' '.join(generator_args)}")

            result = subprocess.run(cmd, cwd=build_dir, env=env, capture_output=True, text=True, timeout=300)

            if result.returncode != 0:
                self.logger.error("CMake configuration failed:")
                self.logger.error(f"stdout: {result.stdout}")
                self.logger.error(f"stderr: {result.stderr}")
                return False, result.stderr

            self.logger.info("CMake configuration successful")
            return True, result.stdout

        except subprocess.TimeoutExpired:
            return False, "CMake configuration timed out after 300 seconds"
        except Exception as e:
            return False, f"CMake configuration error: {e}"

    def find_cmake_version_dir(self, build_dir: Path) -> Optional[str]:
        """Find the CMake version directory in CMakeFiles."""
        cmake_files_dir = build_dir / "CMakeFiles"
        if not cmake_files_dir.exists():
            return None

        # Look for version directories (e.g., "3.28.1")
        version_pattern = re.compile(r"^\d+\.\d+\.\d+$")
        for item in cmake_files_dir.iterdir():
            if item.is_dir() and version_pattern.match(item.name):
                return item.name

        return None

    def sanitize_cmake_cache(
        self, cache_file: Path, c_compiler: Optional[str], cxx_compiler: Optional[str]
    ) -> List[str]:
        """Sanitize CMakeCache.txt to make it portable."""
        cache_content = cache_file.read_text().splitlines()
        sanitized_cache = []

        for line in cache_content:
            # Skip project-specific directory paths
            if re.match(r"^(CMAKE_CACHEFILE_DIR|CMAKE_HOME_DIRECTORY|.*_BINARY_DIR|.*_SOURCE_DIR):", line):
                continue

            # Replace absolute paths in compiler-related variables
            if re.match(r"^CMAKE_C_COMPILER:FILEPATH=(.+)$", line) and c_compiler:
                sanitized_cache.append(f"CMAKE_C_COMPILER:FILEPATH={c_compiler}")
            elif re.match(r"^CMAKE_CXX_COMPILER:FILEPATH=(.+)$", line) and cxx_compiler:
                sanitized_cache.append(f"CMAKE_CXX_COMPILER:FILEPATH={cxx_compiler}")
            elif re.match(r"^CMAKE_.*_FLAGS.*=.*", line):
                sanitized_cache.append(line)
            elif re.match(r"^CMAKE_.*(LOADED|INITIALIZED|WORKS|COMPILED):INTERNAL=", line):
                sanitized_cache.append(line)
            elif re.match(r"^CMAKE_BUILD_TYPE:", line):
                sanitized_cache.append(line)
            elif re.match(r"^CMAKE_EXECUTABLE_SUFFIX:", line):
                sanitized_cache.append(line)
            elif line.startswith("#") or line.strip() == "":
                sanitized_cache.append(line)

        # Add essential cache variables if missing
        essential_vars = ["CMAKE_PLATFORM_INFO_INITIALIZED:INTERNAL=1"]

        if c_compiler:
            essential_vars.append("CMAKE_C_COMPILER_LOADED:INTERNAL=1")

        if cxx_compiler:
            essential_vars.append("CMAKE_CXX_COMPILER_LOADED:INTERNAL=1")

        for var in essential_vars:
            var_name = var.split(":")[0]
            if not any(line.startswith(f"{var_name}:") for line in sanitized_cache):
                sanitized_cache.append(var)

        return sanitized_cache

    def create_usage_instructions(
        self,
        cmake_version: str,
        c_compiler: Optional[str],
        c_flags: Optional[str],
        cxx_compiler: Optional[str],
        cxx_flags: Optional[str],
    ) -> str:
        """Create usage instructions README content."""
        compiler_info = []
        if c_compiler:
            compiler_info.append(f"- C Compiler: {c_compiler}")
            if c_flags:
                compiler_info.append(f"- C Compiler Flags: {c_flags}")

        if cxx_compiler:
            compiler_info.append(f"- C++ Compiler: {cxx_compiler}")
            if cxx_flags:
                compiler_info.append(f"- C++ Compiler Flags: {cxx_flags}")

        generated_files = ["- CMakeCache.txt: Sanitized cache variables (project paths removed)"]
        if c_compiler:
            generated_files.append(
                f"- CMakeFiles/{cmake_version}/CMakeCCompiler.cmake: Complete C compiler detection results"
            )
        if cxx_compiler:
            generated_files.append(
                f"- CMakeFiles/{cmake_version}/CMakeCXXCompiler.cmake: Complete C++ compiler detection results"
            )
        generated_files.append(f"- CMakeFiles/{cmake_version}/CMakeSystem.cmake: System information")

        platform_name = "Windows" if self.platform == LibraryPlatform.Windows else "Unix"

        usage_instructions = f"""# CMake Compiler Cache - Extracted from Real CMake

## Generated Files:
{chr(10).join(generated_files)}

## Source Information:
{chr(10).join(compiler_info)}
- CMake Version: {cmake_version}
- Platform: {platform_name}
- Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

## How to Use:
1. Copy these files to your CMake build directory BEFORE running cmake
2. Ensure the compiler path is still accessible in the target environment
3. Run cmake as usual - it should skip compiler detection phases

## Example Usage:
```bash
# Extract cache files to new build directory
unzip cmake-compiler-cache.zip -d ./new-build/

# Run cmake (should skip "Check for working CXX compiler", "Detecting CXX compiler ABI info", etc.)
cd new-build
cmake ../your-project
```

## What Gets Skipped:
"""

        if c_compiler:
            usage_instructions += """- [SKIP] "The C compiler identification is [compiler]"
- [SKIP] "Detecting C compiler ABI info"
- [SKIP] "Check for working C compiler"
- [SKIP] "Detecting C compile features"
"""

        if cxx_compiler:
            usage_instructions += """- [SKIP] "The CXX compiler identification is [compiler]"
- [SKIP] "Detecting CXX compiler ABI info"
- [SKIP] "Check for working CXX compiler"
- [SKIP] "Detecting CXX compile features"
"""

        usage_instructions += """
## Notes:
- These files are specific to the exact compiler path and version
- If the compiler moves or version changes, regenerate the cache
- The cache includes comprehensive feature detection that our manual script couldn't replicate
- This is the same mechanism CMake uses internally for caching
"""

        return usage_instructions

    def upload_to_s3(self, zip_file_path: Path, compiler_id: str) -> Tuple[bool, str]:
        """
        Upload a CMake cache ZIP file to S3.

        Args:
            zip_file_path: Path to the ZIP file to upload
            compiler_id: Compiler identifier for the S3 key

        Returns:
            Tuple of (success: bool, message: str)
        """
        try:
            # S3 key format: compiler-cmake-cache/{compiler_id}.zip
            s3_key = f"compiler-cmake-cache/{compiler_id}.zip"

            self.logger.info(f"Uploading {zip_file_path} to s3://{S3_STORAGE_BUCKET}/{s3_key}")

            # Prepare extra args for upload
            extra_args = {
                "ContentType": "application/zip",
                "Metadata": {
                    "compiler-id": compiler_id,
                    "upload-date": datetime.now().isoformat(),
                    "generated-by": "compiler-explorer-infra",
                },
            }

            # Upload the file
            s3_client.upload_file(str(zip_file_path), S3_STORAGE_BUCKET, s3_key, ExtraArgs=extra_args)

            s3_url = f"https://{S3_STORAGE_BUCKET}/{s3_key}"
            self.logger.info(f"Successfully uploaded to: {s3_url}")

            return True, f"Uploaded to {s3_url}"

        except Exception as e:
            error_msg = f"Failed to upload to S3: {e}"
            self.logger.error(error_msg)
            return False, error_msg

    def extract_cache(
        self,
        c_compiler_path: Optional[str] = None,
        c_flags: Optional[str] = None,
        cxx_compiler_path: Optional[str] = None,
        cxx_flags: Optional[str] = None,
        output_dir: Optional[Path] = None,
        create_zip: bool = True,
        keep_temp_dir: bool = False,
        compiler_id: Optional[str] = None,
        upload_to_s3: bool = False,
        compiler_info: Optional[CompilerInfo] = None,
    ) -> Tuple[bool, str]:
        """
        Extract CMake compiler cache files.

        Args:
            c_compiler_path: Path to C compiler (uses CC env var if not specified)
            c_flags: C compiler flags (uses CFLAGS env var if not specified)
            cxx_compiler_path: Path to C++ compiler (uses CXX env var if not specified)
            cxx_flags: C++ compiler flags (uses CXXFLAGS env var if not specified)
            output_dir: Output directory (default: ./cmake-cache-extracted)
            create_zip: Create zip file with cache files
            keep_temp_dir: Keep temporary directory for inspection
            compiler_id: Compiler identifier (used in ZIP filename if provided)
            upload_to_s3: Upload ZIP file to S3 after creation
            compiler_info: CompilerInfo object with full compiler properties

        Returns:
            Tuple of (success: bool, message: str)
        """
        # Use environment variables if not provided
        c_compiler_path = c_compiler_path or os.environ.get("CC")
        c_flags = c_flags or os.environ.get("CFLAGS")
        cxx_compiler_path = cxx_compiler_path or os.environ.get("CXX")
        cxx_flags = cxx_flags or os.environ.get("CXXFLAGS")

        # Validate - at least one compiler must be specified
        if not c_compiler_path and not cxx_compiler_path:
            return False, "No compiler specified. Set CC and/or CXX environment variables or use parameters."

        # Resolve compiler paths
        c_compiler_full = None
        cxx_compiler_full = None

        if c_compiler_path:
            c_compiler_full = self.resolve_compiler_path(c_compiler_path)
            if not c_compiler_full:
                return False, f"C compiler not found: {c_compiler_path}"
            self.logger.info(f"Using C compiler: {c_compiler_full}")

        if cxx_compiler_path:
            cxx_compiler_full = self.resolve_compiler_path(cxx_compiler_path)
            if not cxx_compiler_full:
                return False, f"C++ compiler not found: {cxx_compiler_path}"
            self.logger.info(f"Using C++ compiler: {cxx_compiler_full}")

        # Create temporary directory
        temp_dir = Path(tempfile.mkdtemp(prefix="cmake-cache-extract-"))
        self.logger.info(f"Creating temporary project in: {temp_dir}")

        try:
            # Create minimal CMake project
            self.create_minimal_cmake_project(temp_dir, c_compiler_full, cxx_compiler_full)

            # Create build directory
            build_dir = temp_dir / "build"
            build_dir.mkdir()

            # Set up compiler environment using the proper method
            if compiler_info:
                # Use the provided compiler info with full properties
                env = self.setup_compiler_environment_from_properties(compiler_info)
            else:
                # Fallback to basic environment
                env = os.environ.copy()
                if c_compiler_full:
                    env["CC"] = c_compiler_full
                if cxx_compiler_full:
                    env["CXX"] = cxx_compiler_full
                if c_flags:
                    env["CFLAGS"] = c_flags
                if cxx_flags:
                    env["CXXFLAGS"] = cxx_flags

            try:
                # Run CMake configuration
                success, message = self.run_cmake_configuration(build_dir, env)
                if not success:
                    return False, f"CMake configuration failed: {message}"

                # Find CMake version directory
                cmake_version = self.find_cmake_version_dir(build_dir)
                if not cmake_version:
                    return False, "Could not find CMake version directory"

                self.logger.info(f"Found CMake version: {cmake_version}")

                # Create output directory
                if output_dir is None:
                    output_dir = Path("./cmake-cache-extracted")

                output_dir = Path(output_dir)
                output_dir.mkdir(parents=True, exist_ok=True)

                cmake_files_dir = build_dir / "CMakeFiles"
                cmake_version_dir = cmake_files_dir / cmake_version

                output_cmake_files_dir = output_dir / "CMakeFiles"
                output_version_dir = output_cmake_files_dir / cmake_version
                output_version_dir.mkdir(parents=True, exist_ok=True)

                # Copy essential files
                files_to_copy = [
                    (build_dir / "CMakeCache.txt", output_dir / "CMakeCache.txt", "Main cache file"),
                    (
                        cmake_version_dir / "CMakeSystem.cmake",
                        output_version_dir / "CMakeSystem.cmake",
                        "System information",
                    ),
                ]

                if c_compiler_full:
                    files_to_copy.append(
                        (
                            cmake_version_dir / "CMakeCCompiler.cmake",
                            output_version_dir / "CMakeCCompiler.cmake",
                            "C compiler detection",
                        )
                    )

                if cxx_compiler_full:
                    files_to_copy.append(
                        (
                            cmake_version_dir / "CMakeCXXCompiler.cmake",
                            output_version_dir / "CMakeCXXCompiler.cmake",
                            "C++ compiler detection",
                        )
                    )

                self.logger.info("Extracting reusable cache files...")

                for source, dest, description in files_to_copy:
                    if source.exists():
                        shutil.copy2(source, dest)
                        self.logger.debug(f"Copied: {description}")
                    else:
                        self.logger.warning(f"Missing file: {source}")

                # Sanitize CMakeCache.txt
                sanitized_cache = self.sanitize_cmake_cache(
                    output_dir / "CMakeCache.txt", c_compiler_full, cxx_compiler_full
                )
                (output_dir / "CMakeCache.txt").write_text("\n".join(sanitized_cache))

                # Create usage instructions
                readme_content = self.create_usage_instructions(
                    cmake_version, c_compiler_full, c_flags, cxx_compiler_full, cxx_flags
                )
                (output_dir / "README.md").write_text(readme_content)

                self.logger.info("Generated cache files:")
                self.logger.info("  - CMakeCache.txt (sanitized)")
                if c_compiler_full:
                    self.logger.info(f"  - CMakeFiles/{cmake_version}/CMakeCCompiler.cmake")
                if cxx_compiler_full:
                    self.logger.info(f"  - CMakeFiles/{cmake_version}/CMakeCXXCompiler.cmake")
                self.logger.info(f"  - CMakeFiles/{cmake_version}/CMakeSystem.cmake")
                self.logger.info("  - README.md")

                # Create zip file if requested
                if create_zip:
                    if compiler_id:
                        zip_filename = f"cmake-compiler-cache-{compiler_id}.zip"
                    else:
                        zip_filename = "cmake-compiler-cache-extracted.zip"
                    zip_file = output_dir.parent / zip_filename
                    if zip_file.exists():
                        zip_file.unlink()

                    self.logger.info("Creating zip archive...")
                    with zipfile.ZipFile(zip_file, "w", zipfile.ZIP_DEFLATED) as zf:
                        for file_path in output_dir.rglob("*"):
                            if file_path.is_file():
                                arcname = file_path.relative_to(output_dir)
                                zf.write(file_path, arcname)

                    zip_size_mb = round(zip_file.stat().st_size / (1024 * 1024), 2)
                    self.logger.info(f"Created: {zip_file}")
                    self.logger.info(f"  Size: {zip_size_mb} MB")

                    # Upload to S3 if requested
                    if upload_to_s3 and compiler_id:
                        upload_success, upload_message = self.upload_to_s3(zip_file, compiler_id)
                        if not upload_success:
                            # Log the error but don't fail the entire operation
                            self.logger.warning(f"S3 upload failed: {upload_message}")

                self.logger.info("\nCompiler cache extraction complete!")
                self.logger.info("This cache was generated by CMake itself and includes:")
                self.logger.info("  - Complete compiler feature detection")
                self.logger.info("  - ABI information and toolchain tools")
                self.logger.info("  - System-specific configuration")
                self.logger.info("  - All version-specific optimizations")

                return True, f"Cache extracted successfully to {output_dir}"

            finally:
                pass  # Environment cleanup not needed here since we're using library_builder logic

        finally:
            # Clean up temporary directory
            if temp_dir.exists():
                if keep_temp_dir:
                    self.logger.info(f"Temporary directory preserved: {temp_dir}")
                else:
                    shutil.rmtree(temp_dir, ignore_errors=True)
