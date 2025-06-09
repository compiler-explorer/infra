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

from lib.amazon_properties import get_properties_compilers_and_libraries
from lib.library_platform import LibraryPlatform


class CompilerInfo:
    """Typed wrapper around compiler properties with convenience methods."""

    def __init__(self, compiler_id: str, props: dict):
        self.id = compiler_id
        self._props = props

    @property
    def executable(self) -> str:
        return self._props.get("exe", "")

    @property
    def compiler_type(self) -> str:
        return self._props.get("compilerType", "")

    @property
    def options(self) -> str:
        return self._props.get("options", "")

    @property
    def include_path(self) -> str:
        return self._props.get("includePath", "")

    @property
    def lib_path(self) -> str:
        return self._props.get("libPath", "")

    @property
    def ld_path(self) -> str:
        return self._props.get("ldPath", "")

    @property
    def is_msvc(self) -> bool:
        return self.compiler_type == "win32-vc"

    @property
    def is_clang(self) -> bool:
        return self.compiler_type == "clang"

    @property
    def is_gcc_like(self) -> bool:
        return self.compiler_type in ["", "gcc"]

    @property
    def exists(self) -> bool:
        """Check if the compiler executable exists on the filesystem."""
        return bool(self.executable and Path(self.executable).exists())

    def get_c_compiler(self) -> str:
        """
        Derive C compiler path from C++ compiler path.
        This logic is extracted from library_builder.py writebuildscript()
        """
        exe = self.executable

        # Special case for EDG compilers
        if self.compiler_type == "edg":
            return exe

        # Windows executable handling
        if exe.endswith(".exe"):
            compilerexecc = exe.replace("++.exe", "")
            if exe.endswith("clang++.exe"):
                compilerexecc = f"{compilerexecc}.exe"
            elif exe.endswith("g++.exe"):
                compilerexecc = f"{compilerexecc}cc.exe"
            elif self.compiler_type == "edg":
                compilerexecc = exe
            else:
                if not compilerexecc.endswith(".exe"):
                    compilerexecc = compilerexecc + ".exe"
            return compilerexecc

        # Linux/Unix executable handling
        else:
            compilerexecc = exe[:-2]  # Remove last 2 chars (++)
            if exe.endswith("clang++"):
                compilerexecc = f"{compilerexecc}"  # clang++ -> clang
            elif exe.endswith("g++"):
                compilerexecc = f"{compilerexecc}cc"  # g++ -> gcc
            elif self.compiler_type == "edg":
                compilerexecc = exe
            return compilerexecc


class PlatformEnvironmentManager:
    """Handles cross-platform environment variable management."""

    def __init__(self, platform: LibraryPlatform):
        self.platform = platform

    def get_library_paths(self, compiler: CompilerInfo, toolchain: str, arch: str) -> list:
        """
        Determine library paths for a compiler based on platform and architecture.
        This logic is extracted from library_builder.py writebuildscript()
        """
        libparampaths = []

        if compiler.is_msvc:
            # MSVC uses libPath from compiler properties
            if compiler.lib_path:
                libparampaths = compiler.lib_path.split(";")
        else:
            # Unix-like systems use toolchain-based paths
            if arch == "" or arch == "x86_64":
                # Native arch for the compiler, so most of the time 64, but not always
                if os.path.exists(f"{toolchain}/lib64"):
                    libparampaths.append(f"{toolchain}/lib64")
                    libparampaths.append(f"{toolchain}/lib")
                else:
                    libparampaths.append(f"{toolchain}/lib")
            elif arch == "x86":
                libparampaths.append(f"{toolchain}/lib")
                if os.path.exists(f"{toolchain}/lib32"):
                    libparampaths.append(f"{toolchain}/lib32")

        return libparampaths

    def get_arch_flags(self, compiler: CompilerInfo, arch: str) -> str:
        """
        Get architecture-specific flags for a compiler.
        This logic is extracted from library_builder.py writebuildscript()
        """
        if arch != "x86":
            return ""

        if compiler.compiler_type == "clang" or compiler.compiler_type == "win32-mingw-clang":
            return "-m32"
        elif (
            compiler.compiler_type == ""
            or compiler.compiler_type == "gcc"
            or compiler.compiler_type == "win32-mingw-gcc"
        ):
            return "-march=i386 -m32"

        return ""

    def get_rpath_flags(self, compiler: CompilerInfo, libparampaths: list) -> str:
        """
        Generate rpath flags for Unix-like systems.
        This logic is extracted from library_builder.py writebuildscript()
        """
        if compiler.compiler_type == "edg" or compiler.is_msvc:
            return ""

        rpathflags = ""
        for path in libparampaths:
            rpathflags += f"-Wl,-rpath={path} "

        return rpathflags.strip()

    def get_ld_flags(self, compiler: CompilerInfo, libparampaths: list) -> str:
        """
        Generate linker flags for Unix-like systems.
        This logic is extracted from library_builder.py writebuildscript()
        """
        if compiler.is_msvc:
            return ""

        ldflags = ""
        for path in libparampaths:
            if path != "":
                ldflags += f"-L{path} "

        return ldflags.strip()

    def setup_compiler_environment(self, compiler: CompilerInfo, toolchain: str = "", arch: str = "") -> Dict[str, str]:
        """Set up environment variables for a compiler in a platform-aware way."""
        env = os.environ.copy()

        # Set basic compiler environment
        env["CC"] = compiler.get_c_compiler()
        env["CXX"] = compiler.executable

        # Determine toolchain if not provided
        if not toolchain:
            toolchain = str(Path(compiler.executable).parent / "..")

        # Get library paths
        libparampaths = self.get_library_paths(compiler, toolchain, arch)

        if self.platform == LibraryPlatform.Windows and compiler.is_msvc:
            # Windows MSVC setup
            if compiler.include_path:
                env["INCLUDE"] = compiler.include_path
            if compiler.lib_path:
                env["LIB"] = compiler.lib_path

            # Add compiler directory to PATH
            compiler_dir = str(Path(compiler.executable).parent)
            self._append_to_path(env, compiler_dir)

            # Add x64 path for DLLs (MSVC specific)
            # Extra path is needed for MSVC, because .dll's are placed in the x64 path
            x64_path = Path(compiler.executable).parent / "../x64"
            if x64_path.exists():
                self._append_to_path(env, str(x64_path.resolve()))

        else:
            # Linux/Unix setup
            compiler_dir = str(Path(compiler.executable).parent)
            self._append_to_path(env, compiler_dir)

            # Set up LD_LIBRARY_PATH
            if compiler.ld_path:
                ld_lib_paths = compiler.ld_path.replace("${exePath}", os.path.dirname(compiler.executable)).replace(
                    "|", ":"
                )
                env["LD_LIBRARY_PATH"] = ld_lib_paths

            # Set up LDFLAGS with library paths and rpath
            ldflags = self.get_ld_flags(compiler, libparampaths)
            rpathflags = self.get_rpath_flags(compiler, libparampaths)
            if ldflags or rpathflags:
                env["LDFLAGS"] = f"{ldflags} {rpathflags}".strip()

        # Set compiler flags if available
        if compiler.options:
            env["CFLAGS"] = compiler.options
            env["CXXFLAGS"] = compiler.options

        return env

    def _append_to_path(self, env: Dict[str, str], path: str) -> None:
        """Append a path to the PATH environment variable in a platform-specific way."""
        separator = ";" if self.platform == LibraryPlatform.Windows else ":"
        if "PATH" in env:
            env["PATH"] = f"{path}{separator}{env['PATH']}"
        else:
            env["PATH"] = path

    def script_env_command(self, var_name: str, var_value: str) -> str:
        """Generate platform-specific environment variable setting command for scripts."""
        if self.platform == LibraryPlatform.Linux:
            return f'export {var_name}="{var_value}"\n'
        elif self.platform == LibraryPlatform.Windows:
            escaped_var_value = var_value.replace('"', '`"')
            return f'$env:{var_name}="{escaped_var_value}"\n'
        else:
            raise ValueError(f"Unsupported platform: {self.platform}")


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
                    # For Windows, only support MSVC compilers
                    if not compiler_info.is_msvc:
                        continue
                else:
                    # For Linux, support GCC, Clang, and other Unix compilers
                    if compiler_info.is_msvc:
                        continue

            supported[compiler_id] = compiler_info

        self.logger.info(f"Found {len(supported)} supported compilers on {self.platform.value}")
        return supported


class ScriptExecutor:
    """Unified script execution with consistent error handling."""

    def __init__(self, logger, platform: LibraryPlatform):
        self.logger = logger
        self.platform = platform

    def check_powershell_available(self) -> bool:
        """Check if PowerShell Core (pwsh) is available."""
        try:
            subprocess.run(["pwsh", "--version"], capture_output=True, check=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            self.logger.error("PowerShell Core (pwsh) is required but not found. Please install PowerShell Core.")
            return False

    def execute_powershell(
        self,
        script_path: Path,
        args: list = None,
        env: Dict[str, str] = None,
        timeout: int = 300,
        cwd: Optional[str] = None,
    ) -> Tuple[bool, str, str]:
        """
        Execute PowerShell script with standardized error handling.

        Returns:
            Tuple of (success: bool, stdout: str, stderr: str)
        """
        if not self.check_powershell_available():
            return False, "", "PowerShell Core not available"

        cmd = ["pwsh", str(script_path)]
        if args:
            cmd.extend(args)

        try:
            self.logger.info(f"Running: {' '.join(cmd)}")
            result = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=timeout, cwd=cwd)

            success = result.returncode == 0
            if success:
                self.logger.debug(f"Script succeeded: {script_path}")
            else:
                self.logger.error(f"Script failed with return code {result.returncode}: {script_path}")
                self.logger.error(f"Stdout: {result.stdout}")
                self.logger.error(f"Stderr: {result.stderr}")

            return success, result.stdout, result.stderr

        except subprocess.TimeoutExpired:
            self.logger.error(f"Script execution timed out after {timeout} seconds: {script_path}")
            return False, "", f"Timeout after {timeout} seconds"
        except Exception as e:
            self.logger.error(f"Error executing script {script_path}: {e}")
            return False, "", str(e)

    def execute_shell_script(
        self, script_path: Path, env: Dict[str, str] = None, timeout: int = 300, cwd: Optional[str] = None
    ) -> Tuple[bool, str, str]:
        """
        Execute shell script based on platform.

        Returns:
            Tuple of (success: bool, stdout: str, stderr: str)
        """
        if self.platform == LibraryPlatform.Windows:
            # Use PowerShell for Windows scripts
            return self.execute_powershell(script_path, env=env, timeout=timeout, cwd=cwd)
        else:
            # Use bash for Linux scripts
            try:
                cmd = [str(script_path)]
                self.logger.info(f"Running: {' '.join(cmd)}")

                result = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=timeout, cwd=cwd)

                success = result.returncode == 0
                if success:
                    self.logger.debug(f"Script succeeded: {script_path}")
                else:
                    self.logger.error(f"Script failed with return code {result.returncode}: {script_path}")

                return success, result.stdout, result.stderr

            except subprocess.TimeoutExpired:
                self.logger.error(f"Script execution timed out after {timeout} seconds: {script_path}")
                return False, "", f"Timeout after {timeout} seconds"
            except Exception as e:
                self.logger.error(f"Error executing script {script_path}: {e}")
                return False, "", str(e)


class CMakeCacheExtractor:
    """
    Extracts and packages CMake compiler cache files for reuse across projects.

    This class replicates the functionality of Extract-CMakeCache.ps1 in pure Python,
    providing a cross-platform solution for generating CMake compiler cache files.
    """

    def __init__(self, logger, platform: LibraryPlatform = None):
        self.logger = logger
        self.platform = platform or LibraryPlatform.Linux

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

    def run_cmake_configuration(self, build_dir: Path, env: Dict[str, str]) -> Tuple[bool, str]:
        """Run CMake configuration in the build directory."""
        try:
            self.logger.info("Running CMake to detect compiler...")

            cmd = ["cmake", ".."]
            result = subprocess.run(cmd, cwd=build_dir, env=env, capture_output=True, text=True, timeout=300)

            if result.returncode != 0:
                self.logger.error("CMake configuration failed:")
                self.logger.error(f"stdout: {result.stdout}")
                self.logger.error(f"stderr: {result.stderr}")
                return False, result.stderr

            self.logger.info("✓ CMake configuration successful")
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
            usage_instructions += """- ✅ "The C compiler identification is [compiler]"
- ✅ "Detecting C compiler ABI info"
- ✅ "Check for working C compiler"
- ✅ "Detecting C compile features"
"""

        if cxx_compiler:
            usage_instructions += """- ✅ "The CXX compiler identification is [compiler]"
- ✅ "Detecting CXX compiler ABI info"
- ✅ "Check for working CXX compiler"
- ✅ "Detecting CXX compile features"
"""

        usage_instructions += """
## Notes:
- These files are specific to the exact compiler path and version
- If the compiler moves or version changes, regenerate the cache
- The cache includes comprehensive feature detection that our manual script couldn't replicate
- This is the same mechanism CMake uses internally for caching
"""

        return usage_instructions

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

            # Set up environment
            env = os.environ.copy()
            original_env = {}

            # Store and set environment variables
            for var_name, var_value in [
                ("CC", c_compiler_full),
                ("CFLAGS", c_flags),
                ("CXX", cxx_compiler_full),
                ("CXXFLAGS", cxx_flags),
            ]:
                if var_value:
                    original_env[var_name] = env.get(var_name)
                    env[var_name] = var_value

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
                        self.logger.debug(f"✓ Copied: {description}")
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

                self.logger.info("✓ Generated cache files:")
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
                    self.logger.info(f"✓ Created: {zip_file}")
                    self.logger.info(f"  Size: {zip_size_mb} MB")

                self.logger.info("\n✅ Compiler cache extraction complete!")
                self.logger.info("This cache was generated by CMake itself and includes:")
                self.logger.info("  ➤ Complete compiler feature detection")
                self.logger.info("  ➤ ABI information and toolchain tools")
                self.logger.info("  ➤ System-specific configuration")
                self.logger.info("  ➤ All version-specific optimizations")

                return True, f"Cache extracted successfully to {output_dir}"

            finally:
                # Restore environment variables
                for var_name, original_value in original_env.items():
                    if original_value is not None:
                        env[var_name] = original_value
                    elif var_name in env:
                        del env[var_name]

        finally:
            # Clean up temporary directory
            if temp_dir.exists():
                if keep_temp_dir:
                    self.logger.info(f"Temporary directory preserved: {temp_dir}")
                else:
                    shutil.rmtree(temp_dir, ignore_errors=True)
