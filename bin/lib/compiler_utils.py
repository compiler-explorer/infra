#!/usr/bin/env python3

import os
import subprocess
from pathlib import Path
from typing import Dict, Optional, Tuple

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
        elif compiler.compiler_type == "" or compiler.compiler_type == "gcc" or compiler.compiler_type == "win32-mingw-gcc":
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
                ld_lib_paths = compiler.ld_path.replace("${exePath}", os.path.dirname(compiler.executable)).replace("|", ":")
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
        self._props_cache: Dict[str, Tuple] = {}
    
    def get_compiler_properties(self, language: str, force_reload: bool = False) -> Tuple[Dict, Dict]:
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
        cwd: Optional[str] = None
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
            result = subprocess.run(
                cmd,
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=cwd
            )
            
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
        self,
        script_path: Path,
        env: Dict[str, str] = None,
        timeout: int = 300,
        cwd: Optional[str] = None
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
                
                result = subprocess.run(
                    cmd,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    cwd=cwd
                )
                
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