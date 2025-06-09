#!/usr/bin/env python3

import subprocess
from pathlib import Path
from typing import Dict, Optional, Tuple

from lib.library_platform import LibraryPlatform


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