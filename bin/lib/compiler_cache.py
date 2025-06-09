#!/usr/bin/env python3

import logging
import os
import subprocess
from pathlib import Path
from typing import Optional

from lib.amazon_properties import get_properties_compilers_and_libraries
from lib.library_platform import LibraryPlatform


class CompilerCacheExtractor:
    """Handles CMake cache extraction for compilers."""
    
    def __init__(self, logger, staging_dir: Optional[str] = None, dest: Optional[str] = None, platform: Optional[LibraryPlatform] = None):
        self.logger = logger
        self.platform = platform or LibraryPlatform.Linux
        if self.platform == LibraryPlatform.Windows:
            self.staging_dir = staging_dir or "C:/tmp/staging"
            self.dest = dest or "C:/tmp/staging"
        else:
            self.staging_dir = staging_dir or "/tmp/staging"
            self.dest = dest or "/tmp/staging"
        self.compilerprops = None
        
    def load_compilers(self):
        """Load compiler properties for the specified platform."""
        try:
            [self.compilerprops, _] = get_properties_compilers_and_libraries(
                "c++", self.logger, self.platform, True
            )
            self.logger.info(f"Loaded {len(self.compilerprops)} total compilers for {self.platform.value}")
        except Exception as e:
            raise RuntimeError(f"Failed to load compiler properties: {e}")
    
    def get_supported_compilers(self):
        """Get list of supported compilers for the current platform."""
        if not self.compilerprops:
            self.load_compilers()
            
        supported_compilers = {}
        for compiler_id, props in self.compilerprops.items():
            compiler_type = props.get("compilerType", "")
            
            # Check if compiler exists on the system
            compiler_exe = props.get("exe", "")
            if not compiler_exe or not Path(compiler_exe).exists():
                self.logger.debug(f"Skipping {compiler_id}: executable {compiler_exe} not found")
                continue
                
            if self.platform == LibraryPlatform.Windows:
                # For Windows, support MSVC compilers
                if compiler_type == "win32-vc":
                    supported_compilers[compiler_id] = props
            else:
                # For Linux, support GCC, Clang, and other Unix compilers
                if compiler_type in ["", "gcc", "clang"]:  # "" typically means GCC-like
                    supported_compilers[compiler_id] = props
                
        self.logger.info(f"Found {len(supported_compilers)} supported compilers on {self.platform.value}")
        return supported_compilers
    
    def get_windows_compilers(self):
        """Get list of Windows MSVC compilers (legacy method for compatibility)."""
        if self.platform != LibraryPlatform.Windows:
            return {}
        return self.get_supported_compilers()
    
    def setup_compiler_environment(self, compiler_id: str, compiler_props: dict) -> dict:
        """Set up environment variables for a specific compiler."""
        env = os.environ.copy()
        
        # Get compiler executable paths
        compiler_exe = compiler_props["exe"]
        compiler_type = compiler_props.get("compilerType", "")
        
        if self.platform == LibraryPlatform.Windows and compiler_type == "win32-vc":
            # Windows MSVC setup
            compiler_cc = compiler_exe.replace("++.exe", "")
            if not compiler_cc.endswith(".exe"):
                compiler_cc = compiler_cc + ".exe"
                
            # Set MSVC-specific environment variables
            if "includePath" in compiler_props:
                env["INCLUDE"] = compiler_props["includePath"]
            if "libPath" in compiler_props:
                env["LIB"] = compiler_props["libPath"]
                
            # Add compiler directory to PATH
            compiler_dir = str(Path(compiler_exe).parent)
            if "PATH" in env:
                env["PATH"] = f"{compiler_dir};{env['PATH']}"
            else:
                env["PATH"] = compiler_dir
                
        else:
            # Linux/Unix setup (GCC, Clang, etc.)
            if compiler_exe.endswith("++") or "clang++" in compiler_exe or "g++" in compiler_exe:
                # C++ compiler - derive C compiler
                if "clang++" in compiler_exe:
                    compiler_cc = compiler_exe.replace("clang++", "clang")
                elif "g++" in compiler_exe:
                    compiler_cc = compiler_exe.replace("g++", "gcc")
                else:
                    # Generic case: remove ++ suffix
                    compiler_cc = compiler_exe.rstrip("+")
            else:
                # Assume it's a C compiler, derive C++ compiler
                if "clang" in compiler_exe:
                    compiler_cc = compiler_exe
                    compiler_exe = compiler_exe.replace("clang", "clang++")
                elif "gcc" in compiler_exe:
                    compiler_cc = compiler_exe
                    compiler_exe = compiler_exe.replace("gcc", "g++")
                else:
                    # Default case
                    compiler_cc = compiler_exe
                    compiler_exe = compiler_exe + "++"
                    
            # Add compiler directory to PATH (Unix style)
            compiler_dir = str(Path(compiler_exe).parent)
            if "PATH" in env:
                env["PATH"] = f"{compiler_dir}:{env['PATH']}"
            else:
                env["PATH"] = compiler_dir
        
        # Set basic compiler environment
        env["CC"] = compiler_cc
        env["CXX"] = compiler_exe
            
        # Set compiler flags if available
        base_options = compiler_props.get("options", "")
        if base_options:
            # Basic flags for both C and C++
            env["CFLAGS"] = base_options
            env["CXXFLAGS"] = base_options
        
        self.logger.debug(f"Environment setup for {compiler_id} ({compiler_type}):")
        self.logger.debug(f"  CC={env.get('CC')}")
        self.logger.debug(f"  CXX={env.get('CXX')}")
        if self.platform == LibraryPlatform.Windows:
            self.logger.debug(f"  INCLUDE={env.get('INCLUDE', 'Not set')}")
            self.logger.debug(f"  LIB={env.get('LIB', 'Not set')}")
        
        return env
    
    def extract_cache_for_compiler(self, compiler_id: str, compiler_props: dict, output_dir: Path) -> bool:
        """Extract CMake cache for a specific compiler."""
        self.logger.info(f"Extracting cache for compiler: {compiler_id}")
        
        # Set up environment
        env = self.setup_compiler_environment(compiler_id, compiler_props)
        
        # Create compiler-specific output directory
        compiler_output_dir = output_dir / compiler_id
        compiler_output_dir.mkdir(parents=True, exist_ok=True)
        
        # Path to Extract-CMakeCache.ps1 script
        script_path = Path(__file__).parent.parent.parent / "extract-cmakecache" / "Extract-CMakeCache.ps1"
        
        if not script_path.exists():
            self.logger.error(f"Extract-CMakeCache.ps1 script not found at {script_path}")
            return False
            
        # Prepare PowerShell command - works on both Windows and Linux with PowerShell Core
        ps_cmd = [
            "pwsh",
            str(script_path),
            "-OutputDir", str(compiler_output_dir),
            "-ZipOutput:$true"
        ]
        
        # Check if pwsh is available
        try:
            subprocess.run(["pwsh", "--version"], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            self.logger.error("PowerShell Core (pwsh) is required but not found. Please install PowerShell Core.")
            return False
        
        try:
            self.logger.info(f"Running: {' '.join(ps_cmd)}")
            result = subprocess.run(
                ps_cmd,
                env=env,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            
            if result.returncode == 0:
                self.logger.info(f"Successfully extracted cache for {compiler_id}")
                self.logger.debug(f"Output: {result.stdout}")
                return True
            else:
                self.logger.error(f"Cache extraction failed for {compiler_id}")
                self.logger.error(f"Return code: {result.returncode}")
                self.logger.error(f"Stdout: {result.stdout}")
                self.logger.error(f"Stderr: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            self.logger.error(f"Cache extraction timed out for {compiler_id}")
            return False
        except Exception as e:
            self.logger.error(f"Error running cache extraction for {compiler_id}: {e}")
            return False
    
    def extract_all_compilers(self, output_dir: Path, compiler_filter: Optional[str] = None):
        """Extract cache files for all or filtered compilers."""
        compilers = self.get_supported_compilers()
        
        if compiler_filter:
            if compiler_filter not in compilers:
                raise ValueError(f"Compiler '{compiler_filter}' not found. Available: {list(compilers.keys())}")
            compilers = {compiler_filter: compilers[compiler_filter]}
            
        success_count = 0
        failed_count = 0
        
        for compiler_id, compiler_props in compilers.items():
            if self.extract_cache_for_compiler(compiler_id, compiler_props, output_dir):
                success_count += 1
            else:
                failed_count += 1
                
        self.logger.info(f"Cache extraction complete: {success_count} succeeded, {failed_count} failed")
        return success_count, failed_count