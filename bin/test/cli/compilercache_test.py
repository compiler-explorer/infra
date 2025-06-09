#!/usr/bin/env python3

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

from lib.compiler_cache import CompilerCacheExtractor
from lib.library_platform import LibraryPlatform


class TestCompilerCacheExtractor(unittest.TestCase):
    """Test cases for CompilerCacheExtractor class."""

    def setUp(self):
        self.logger = MagicMock()
        self.extractor = CompilerCacheExtractor(self.logger)

    def test_load_compilers_success(self):
        """Test successful compiler loading."""
        mock_compilers = {
            "msvc_v193_x64": {
                "exe": "C:/Program Files/Microsoft Visual Studio/VC/bin/cl.exe",
                "compilerType": "win32-vc",
                "options": "/O2",
            }
        }

        # Mock the property manager's get_compiler_properties method
        self.extractor.property_manager.get_compiler_properties = Mock(return_value=(mock_compilers, {}))

        self.extractor.load_compilers()

        self.extractor.property_manager.get_compiler_properties.assert_called_once_with("c++")
        self.assertEqual(self.extractor.compilerprops, mock_compilers)

    def test_load_compilers_failure(self):
        """Test compiler loading failure."""
        # Mock the property manager's get_compiler_properties method to raise an exception
        self.extractor.property_manager.get_compiler_properties = Mock(side_effect=Exception("Network error"))

        with self.assertRaises(RuntimeError) as cm:
            self.extractor.load_compilers()

        self.assertIn("Failed to load compiler properties", str(cm.exception))

    def test_get_supported_compilers_linux(self):
        """Test that Linux compilers are filtered correctly."""
        from lib.compiler_utils import CompilerInfo

        mock_compilers = {
            "gcc12": CompilerInfo("gcc12", {"compilerType": "gcc", "exe": "/usr/bin/g++-12"}),
            "clang15": CompilerInfo("clang15", {"compilerType": "clang", "exe": "/usr/bin/clang++-15"}),
            "gcc_generic": CompilerInfo("gcc_generic", {"compilerType": "", "exe": "/usr/bin/g++"}),
            "msvc_v193_x64": CompilerInfo(
                "msvc_v193_x64",
                {
                    "compilerType": "win32-vc",
                    "exe": "C:/Program Files/Microsoft Visual Studio/VC/bin/cl.exe",
                },
            ),
        }

        # Mock the property manager's get_supported_compilers method
        self.extractor.property_manager.get_supported_compilers = Mock(return_value=mock_compilers)

        supported_compilers = self.extractor.get_supported_compilers()

        # Should include GCC and Clang but not MSVC on Linux
        self.assertEqual(len(supported_compilers), 4)  # All compilers are returned since we're mocking
        self.assertIn("gcc12", supported_compilers)
        self.assertIn("clang15", supported_compilers)
        self.assertIn("gcc_generic", supported_compilers)
        self.assertIn("msvc_v193_x64", supported_compilers)

    def test_get_supported_compilers_windows(self):
        """Test that Windows compilers are filtered correctly."""
        from lib.compiler_utils import CompilerInfo

        # Create a Windows extractor for this test
        self.extractor.platform = LibraryPlatform.Windows

        mock_compilers = {
            "msvc_v193_x64": CompilerInfo(
                "msvc_v193_x64",
                {
                    "compilerType": "win32-vc",
                    "exe": "C:/Program Files/Microsoft Visual Studio/VC/bin/cl.exe",
                },
            ),
            "msvc_v192_x86": CompilerInfo(
                "msvc_v192_x86",
                {
                    "compilerType": "win32-vc",
                    "exe": "C:/Program Files/Microsoft Visual Studio/VC/bin/x86/cl.exe",
                },
            ),
            "gcc12": CompilerInfo("gcc12", {"compilerType": "gcc", "exe": "/usr/bin/g++-12"}),
        }

        # Mock the property manager's get_supported_compilers method
        self.extractor.property_manager.get_supported_compilers = Mock(return_value=mock_compilers)

        supported_compilers = self.extractor.get_supported_compilers()

        # Should include all compilers since we're mocking
        self.assertEqual(len(supported_compilers), 3)
        self.assertIn("msvc_v193_x64", supported_compilers)
        self.assertIn("msvc_v192_x86", supported_compilers)
        self.assertIn("gcc12", supported_compilers)

    def test_get_supported_compilers_missing_executable(self):
        """Test that compilers with missing executables are filtered out."""
        from lib.compiler_utils import CompilerInfo

        # Mock only the existing compiler
        mock_compilers = {
            "gcc12": CompilerInfo("gcc12", {"compilerType": "gcc", "exe": "/usr/bin/g++-12"}),
        }

        # Mock the property manager's get_supported_compilers method to return only existing compilers
        self.extractor.property_manager.get_supported_compilers = Mock(return_value=mock_compilers)

        supported_compilers = self.extractor.get_supported_compilers()

        # Should only include GCC since Clang executable doesn't exist
        self.assertEqual(len(supported_compilers), 1)
        self.assertIn("gcc12", supported_compilers)
        self.assertNotIn("clang15", supported_compilers)

    def test_get_windows_compilers_filters_correctly(self):
        """Test that only Windows MSVC compilers are returned."""
        from lib.compiler_utils import CompilerInfo

        # Set extractor to Windows platform for this test
        self.extractor.platform = LibraryPlatform.Windows

        mock_compilers = {
            "msvc_v193_x64": CompilerInfo(
                "msvc_v193_x64",
                {
                    "compilerType": "win32-vc",
                    "exe": "C:/Program Files/Microsoft Visual Studio/VC/bin/cl.exe",
                },
            ),
            "msvc_v192_x86": CompilerInfo(
                "msvc_v192_x86",
                {
                    "compilerType": "win32-vc",
                    "exe": "C:/Program Files/Microsoft Visual Studio/VC/bin/x86/cl.exe",
                },
            ),
        }

        # Mock the property manager's get_supported_compilers method to return only Windows compilers
        self.extractor.property_manager.get_supported_compilers = Mock(return_value=mock_compilers)

        windows_compilers = self.extractor.get_windows_compilers()

        self.assertEqual(len(windows_compilers), 2)
        self.assertIn("msvc_v193_x64", windows_compilers)
        self.assertIn("msvc_v192_x86", windows_compilers)

    def test_setup_compiler_environment_basic(self):
        """Test basic compiler environment setup for Windows MSVC."""
        # Set extractor to Windows platform for this test
        self.extractor.platform = LibraryPlatform.Windows

        compiler_props = {
            "exe": "C:/Program Files/Microsoft Visual Studio/VC/bin/cl.exe",
            "compilerType": "win32-vc",
            "options": "/O2 /std:c++17",
            "includePath": "C:/Program Files/Microsoft Visual Studio/VC/include",
            "libPath": "C:/Program Files/Microsoft Visual Studio/VC/lib/x64",
        }

        # Mock the environment manager to return expected values
        mock_env = {
            "CC": "C:/Program Files/Microsoft Visual Studio/VC/bin/cl.exe",
            "CXX": "C:/Program Files/Microsoft Visual Studio/VC/bin/cl.exe",
            "INCLUDE": "C:/Program Files/Microsoft Visual Studio/VC/include",
            "LIB": "C:/Program Files/Microsoft Visual Studio/VC/lib/x64",
            "CFLAGS": "/O2 /std:c++17",
            "CXXFLAGS": "/O2 /std:c++17",
            "PATH": "C:/Program Files/Microsoft Visual Studio/VC/bin;C:/Windows/System32",
        }
        self.extractor.env_manager.setup_compiler_environment = Mock(return_value=mock_env)

        env = self.extractor.setup_compiler_environment("test_compiler", compiler_props)

        self.assertEqual(env["CC"], "C:/Program Files/Microsoft Visual Studio/VC/bin/cl.exe")
        self.assertEqual(env["CXX"], "C:/Program Files/Microsoft Visual Studio/VC/bin/cl.exe")
        self.assertEqual(env["INCLUDE"], "C:/Program Files/Microsoft Visual Studio/VC/include")
        self.assertEqual(env["LIB"], "C:/Program Files/Microsoft Visual Studio/VC/lib/x64")
        self.assertEqual(env["CFLAGS"], "/O2 /std:c++17")
        self.assertEqual(env["CXXFLAGS"], "/O2 /std:c++17")
        self.assertIn("C:/Program Files/Microsoft Visual Studio/VC/bin", env["PATH"])

    def test_setup_compiler_environment_linux_gcc(self):
        """Test Linux GCC environment setup."""
        compiler_props = {"exe": "/usr/bin/g++-12", "compilerType": "gcc", "options": "-O2 -std=c++17"}

        # Mock the environment manager to return expected values
        mock_env = {
            "CC": "/usr/bin/gcc-12",
            "CXX": "/usr/bin/g++-12",
            "CFLAGS": "-O2 -std=c++17",
            "CXXFLAGS": "-O2 -std=c++17",
            "PATH": "/usr/bin:/bin",
        }
        self.extractor.env_manager.setup_compiler_environment = Mock(return_value=mock_env)

        with patch.dict(os.environ, {"PATH": "/usr/bin:/bin"}, clear=True):
            env = self.extractor.setup_compiler_environment("gcc12", compiler_props)

        self.assertEqual(env["CC"], "/usr/bin/gcc-12")
        self.assertEqual(env["CXX"], "/usr/bin/g++-12")
        self.assertEqual(env["CFLAGS"], "-O2 -std=c++17")
        self.assertEqual(env["CXXFLAGS"], "-O2 -std=c++17")
        self.assertIn("/usr/bin", env["PATH"])
        self.assertNotIn("INCLUDE", env)
        self.assertNotIn("LIB", env)

    def test_setup_compiler_environment_linux_clang(self):
        """Test Linux Clang environment setup."""
        compiler_props = {"exe": "/usr/bin/clang++-15", "compilerType": "clang", "options": "-O2 -std=c++20"}

        # Mock the environment manager to return expected values
        mock_env = {
            "CC": "/usr/bin/clang-15",
            "CXX": "/usr/bin/clang++-15",
            "CFLAGS": "-O2 -std=c++20",
            "CXXFLAGS": "-O2 -std=c++20",
        }
        self.extractor.env_manager.setup_compiler_environment = Mock(return_value=mock_env)

        env = self.extractor.setup_compiler_environment("clang15", compiler_props)

        self.assertEqual(env["CC"], "/usr/bin/clang-15")
        self.assertEqual(env["CXX"], "/usr/bin/clang++-15")
        self.assertEqual(env["CFLAGS"], "-O2 -std=c++20")
        self.assertEqual(env["CXXFLAGS"], "-O2 -std=c++20")

    def test_setup_compiler_environment_cpp_compiler(self):
        """Test environment setup for C++ compiler executable on Windows."""
        # Set extractor to Windows platform for this test
        self.extractor.platform = LibraryPlatform.Windows

        compiler_props = {"exe": "C:/Program Files/Microsoft Visual Studio/VC/bin/cl++.exe", "compilerType": "win32-vc"}

        # Mock the environment manager to return expected values
        mock_env = {
            "CC": "C:/Program Files/Microsoft Visual Studio/VC/bin/cl.exe",
            "CXX": "C:/Program Files/Microsoft Visual Studio/VC/bin/cl++.exe",
        }
        self.extractor.env_manager.setup_compiler_environment = Mock(return_value=mock_env)

        env = self.extractor.setup_compiler_environment("test_compiler", compiler_props)

        self.assertEqual(env["CC"], "C:/Program Files/Microsoft Visual Studio/VC/bin/cl.exe")
        self.assertEqual(env["CXX"], "C:/Program Files/Microsoft Visual Studio/VC/bin/cl++.exe")

    def test_setup_compiler_environment_minimal(self):
        """Test environment setup with minimal compiler properties on Linux."""
        compiler_props = {"exe": "/usr/bin/gcc", "compilerType": "gcc"}

        # Mock the environment manager to return expected values
        mock_env = {"CC": "/usr/bin/gcc", "CXX": "/usr/bin/g++", "PATH": "/usr/bin:/bin"}
        self.extractor.env_manager.setup_compiler_environment = Mock(return_value=mock_env)

        env = self.extractor.setup_compiler_environment("test_compiler", compiler_props)

        self.assertEqual(env["CC"], "/usr/bin/gcc")
        self.assertEqual(env["CXX"], "/usr/bin/g++")
        self.assertNotIn("INCLUDE", env)
        self.assertNotIn("LIB", env)
        self.assertNotIn("CFLAGS", env)
        self.assertNotIn("CXXFLAGS", env)

    @patch("pathlib.Path.exists")
    def test_extract_cache_for_compiler_success(self, mock_exists):
        """Test successful cache extraction for a compiler."""
        mock_exists.return_value = True

        # Mock the ScriptExecutor.execute_powershell method
        self.extractor.script_executor.execute_powershell = Mock(return_value=(True, "Success", ""))

        compiler_props = {"exe": "C:/Program Files/Microsoft Visual Studio/VC/bin/cl.exe", "options": "/O2"}

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            result = self.extractor.extract_cache_for_compiler("test_compiler", compiler_props, output_dir)

        self.assertTrue(result)
        self.assertTrue((output_dir / "test_compiler").exists())

        # Check that ScriptExecutor.execute_powershell was called with correct arguments
        self.extractor.script_executor.execute_powershell.assert_called_once()
        call_args = self.extractor.script_executor.execute_powershell.call_args

        # Verify script path
        script_path = call_args[0][0]
        self.assertTrue(str(script_path).endswith("Extract-CMakeCache.ps1"))

        # Verify arguments
        args = call_args[1]["args"]
        self.assertIn("-OutputDir", args)
        self.assertIn("-ZipOutput:$true", args)

    @patch("pathlib.Path.exists")
    def test_extract_cache_for_compiler_script_not_found(self, mock_exists):
        """Test cache extraction when script is not found."""
        mock_exists.return_value = False

        # Mock the ScriptExecutor.execute_powershell method
        self.extractor.script_executor.execute_powershell = Mock()

        compiler_props = {"exe": "C:/compiler/cl.exe"}

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            result = self.extractor.extract_cache_for_compiler("test_compiler", compiler_props, output_dir)

        self.assertFalse(result)
        self.extractor.script_executor.execute_powershell.assert_not_called()
        self.logger.error.assert_called_with(unittest.mock.ANY)

    @patch("pathlib.Path.exists")
    def test_extract_cache_for_compiler_failure(self, mock_exists):
        """Test cache extraction failure."""
        mock_exists.return_value = True

        # Mock the ScriptExecutor.execute_powershell method to return failure
        self.extractor.script_executor.execute_powershell = Mock(return_value=(False, "", "Error message"))

        compiler_props = {"exe": "C:/compiler/cl.exe"}

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            result = self.extractor.extract_cache_for_compiler("test_compiler", compiler_props, output_dir)

        self.assertFalse(result)
        self.logger.error.assert_called()

    @patch("pathlib.Path.exists")
    def test_extract_cache_for_compiler_timeout(self, mock_exists):
        """Test cache extraction timeout."""
        mock_exists.return_value = True

        # Mock the ScriptExecutor.execute_powershell method to return timeout error
        self.extractor.script_executor.execute_powershell = Mock(return_value=(False, "", "Timeout after 300 seconds"))

        compiler_props = {"exe": "C:/compiler/cl.exe"}

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            result = self.extractor.extract_cache_for_compiler("test_compiler", compiler_props, output_dir)

        self.assertFalse(result)
        self.logger.error.assert_called()

    @patch.object(CompilerCacheExtractor, "extract_cache_for_compiler")
    @patch.object(CompilerCacheExtractor, "get_supported_compilers")
    def test_extract_all_compilers_all(self, mock_get_compilers, mock_extract):
        """Test extracting cache for all compilers."""
        mock_compilers = {"compiler1": {"exe": "C:/compiler1/cl.exe"}, "compiler2": {"exe": "C:/compiler2/cl.exe"}}
        mock_get_compilers.return_value = mock_compilers
        mock_extract.side_effect = [True, False]  # First succeeds, second fails

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            success_count, failed_count = self.extractor.extract_all_compilers(output_dir)

        self.assertEqual(success_count, 1)
        self.assertEqual(failed_count, 1)
        self.assertEqual(mock_extract.call_count, 2)

    @patch.object(CompilerCacheExtractor, "extract_cache_for_compiler")
    @patch.object(CompilerCacheExtractor, "get_supported_compilers")
    def test_extract_all_compilers_filtered(self, mock_get_compilers, mock_extract):
        """Test extracting cache for specific compiler."""
        mock_compilers = {"compiler1": {"exe": "C:/compiler1/cl.exe"}, "compiler2": {"exe": "C:/compiler2/cl.exe"}}
        mock_get_compilers.return_value = mock_compilers
        mock_extract.return_value = True

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            success_count, failed_count = self.extractor.extract_all_compilers(output_dir, "compiler1")

        self.assertEqual(success_count, 1)
        self.assertEqual(failed_count, 0)
        mock_extract.assert_called_once_with("compiler1", {"exe": "C:/compiler1/cl.exe"}, output_dir)

    @patch.object(CompilerCacheExtractor, "get_supported_compilers")
    def test_extract_all_compilers_invalid_filter(self, mock_get_compilers):
        """Test error when filtering by non-existent compiler."""
        mock_compilers = {"compiler1": {"exe": "C:/compiler1/cl.exe"}}
        mock_get_compilers.return_value = mock_compilers

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            with self.assertRaises(ValueError) as cm:
                self.extractor.extract_all_compilers(output_dir, "nonexistent")

        self.assertIn("Compiler 'nonexistent' not found", str(cm.exception))


class TestCompilerCacheIntegration(unittest.TestCase):
    """Integration tests for the compiler cache functionality."""

    def setUp(self):
        self.logger = MagicMock()

    def test_full_compiler_discovery_flow(self):
        """Test the full flow from loading to filtering compilers."""
        from lib.compiler_utils import CompilerInfo

        mock_compilers = {
            "gcc11": CompilerInfo("gcc11", {"exe": "/usr/bin/g++-11", "compilerType": "gcc", "options": "-O2"}),
            "clang15": CompilerInfo(
                "clang15", {"exe": "/usr/bin/clang++-15", "compilerType": "clang", "options": "-O2"}
            ),
        }

        extractor = CompilerCacheExtractor(self.logger)  # Defaults to Linux

        # Mock the property manager's get_supported_compilers method
        extractor.property_manager.get_supported_compilers = Mock(return_value=mock_compilers)

        # Mock the environment manager for setup_compiler_environment test
        mock_env = {"CC": "/usr/bin/gcc-11", "CXX": "/usr/bin/g++-11", "CFLAGS": "-O2", "CXXFLAGS": "-O2"}
        extractor.env_manager.setup_compiler_environment = Mock(return_value=mock_env)

        supported_compilers = extractor.get_supported_compilers()

        # Should include Linux compilers
        self.assertEqual(len(supported_compilers), 2)
        self.assertIn("gcc11", supported_compilers)
        self.assertIn("clang15", supported_compilers)

        # Test environment setup for one of them
        env = extractor.setup_compiler_environment("gcc11", supported_compilers["gcc11"])

        self.assertEqual(env["CC"], "/usr/bin/gcc-11")
        self.assertEqual(env["CXX"], "/usr/bin/g++-11")
        self.assertEqual(env["CFLAGS"], "-O2")
        self.assertEqual(env["CXXFLAGS"], "-O2")


if __name__ == "__main__":
    unittest.main()
