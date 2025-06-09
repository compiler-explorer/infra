#!/usr/bin/env python3

import os
import subprocess
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
        
    @patch('lib.compiler_cache.get_properties_compilers_and_libraries')
    def test_load_compilers_success(self, mock_get_props):
        """Test successful compiler loading."""
        mock_compilers = {
            "msvc_v193_x64": {
                "exe": "C:/Program Files/Microsoft Visual Studio/VC/bin/cl.exe",
                "compilerType": "win32-vc",
                "options": "/O2"
            }
        }
        mock_get_props.return_value = [mock_compilers, {}]
        
        self.extractor.load_compilers()
        
        mock_get_props.assert_called_once_with("c++", self.logger, LibraryPlatform.Linux, True)
        self.assertEqual(self.extractor.compilerprops, mock_compilers)
        self.logger.info.assert_called_with("Loaded 1 total compilers for Linux")
        
    @patch('lib.compiler_cache.get_properties_compilers_and_libraries')
    def test_load_compilers_failure(self, mock_get_props):
        """Test compiler loading failure."""
        mock_get_props.side_effect = Exception("Network error")
        
        with self.assertRaises(RuntimeError) as cm:
            self.extractor.load_compilers()
            
        self.assertIn("Failed to load compiler properties", str(cm.exception))
        
    @patch('pathlib.Path.exists')
    def test_get_supported_compilers_linux(self, mock_exists):
        """Test that Linux compilers are filtered correctly."""
        mock_exists.return_value = True  # All compilers exist
        
        self.extractor.compilerprops = {
            "gcc12": {
                "compilerType": "gcc",
                "exe": "/usr/bin/g++-12"
            },
            "clang15": {
                "compilerType": "clang", 
                "exe": "/usr/bin/clang++-15"
            },
            "gcc_generic": {
                "compilerType": "",  # Generic GCC-like
                "exe": "/usr/bin/g++"
            },
            "msvc_v193_x64": {
                "compilerType": "win32-vc",
                "exe": "C:/Program Files/Microsoft Visual Studio/VC/bin/cl.exe"
            }
        }
        
        supported_compilers = self.extractor.get_supported_compilers()
        
        # Should include GCC and Clang but not MSVC on Linux
        self.assertEqual(len(supported_compilers), 3)
        self.assertIn("gcc12", supported_compilers)
        self.assertIn("clang15", supported_compilers)
        self.assertIn("gcc_generic", supported_compilers)
        self.assertNotIn("msvc_v193_x64", supported_compilers)
        
    @patch('pathlib.Path.exists')
    def test_get_supported_compilers_windows(self, mock_exists):
        """Test that Windows compilers are filtered correctly."""
        mock_exists.return_value = True  # All compilers exist
        
        self.extractor.platform = LibraryPlatform.Windows
        self.extractor.compilerprops = {
            "msvc_v193_x64": {
                "compilerType": "win32-vc",
                "exe": "C:/Program Files/Microsoft Visual Studio/VC/bin/cl.exe"
            },
            "msvc_v192_x86": {
                "compilerType": "win32-vc",
                "exe": "C:/Program Files/Microsoft Visual Studio/VC/bin/x86/cl.exe"
            },
            "gcc12": {
                "compilerType": "gcc",
                "exe": "/usr/bin/g++-12"
            }
        }
        
        supported_compilers = self.extractor.get_supported_compilers()
        
        # Should include MSVC but not GCC on Windows
        self.assertEqual(len(supported_compilers), 2)
        self.assertIn("msvc_v193_x64", supported_compilers)
        self.assertIn("msvc_v192_x86", supported_compilers)
        self.assertNotIn("gcc12", supported_compilers)
        
    @patch('lib.compiler_cache.Path')
    def test_get_supported_compilers_missing_executable(self, mock_path):
        """Test that compilers with missing executables are filtered out."""
        # Mock Path constructor to return different mock objects with different exists() behavior
        def path_constructor(path_str):
            mock_path_obj = Mock()
            if "/usr/bin/g++-12" in str(path_str):
                mock_path_obj.exists.return_value = True
            else:
                mock_path_obj.exists.return_value = False
            return mock_path_obj
            
        mock_path.side_effect = path_constructor
        
        self.extractor.compilerprops = {
            "gcc12": {
                "compilerType": "gcc",
                "exe": "/usr/bin/g++-12"
            },
            "clang15": {
                "compilerType": "clang",
                "exe": "/usr/bin/clang++-15"  # This one doesn't exist
            }
        }
        
        supported_compilers = self.extractor.get_supported_compilers()
        
        # Should only include GCC since Clang executable doesn't exist
        self.assertEqual(len(supported_compilers), 1)
        self.assertIn("gcc12", supported_compilers)
        self.assertNotIn("clang15", supported_compilers)
        
    @patch('pathlib.Path.exists')
    def test_get_windows_compilers_filters_correctly(self, mock_exists):
        """Test that only Windows MSVC compilers are returned."""
        mock_exists.return_value = True  # All compilers exist
        
        # Set extractor to Windows platform for this test
        self.extractor.platform = LibraryPlatform.Windows
        self.extractor.compilerprops = {
            "msvc_v193_x64": {
                "compilerType": "win32-vc",
                "exe": "C:/Program Files/Microsoft Visual Studio/VC/bin/cl.exe"
            },
            "gcc_11": {
                "compilerType": "gcc", 
                "exe": "/usr/bin/gcc"
            },
            "clang_15": {
                "compilerType": "clang",
                "exe": "/usr/bin/clang"
            },
            "msvc_v192_x86": {
                "compilerType": "win32-vc",
                "exe": "C:/Program Files/Microsoft Visual Studio/VC/bin/x86/cl.exe"
            }
        }
        
        windows_compilers = self.extractor.get_windows_compilers()
        
        self.assertEqual(len(windows_compilers), 2)
        self.assertIn("msvc_v193_x64", windows_compilers)
        self.assertIn("msvc_v192_x86", windows_compilers)
        self.assertNotIn("gcc_11", windows_compilers)
        self.assertNotIn("clang_15", windows_compilers)
        
    def test_setup_compiler_environment_basic(self):
        """Test basic compiler environment setup for Windows MSVC."""
        # Set extractor to Windows platform for this test
        self.extractor.platform = LibraryPlatform.Windows
        
        compiler_props = {
            "exe": "C:/Program Files/Microsoft Visual Studio/VC/bin/cl.exe",
            "compilerType": "win32-vc",
            "options": "/O2 /std:c++17",
            "includePath": "C:/Program Files/Microsoft Visual Studio/VC/include",
            "libPath": "C:/Program Files/Microsoft Visual Studio/VC/lib/x64"
        }
        
        with patch.dict(os.environ, {"PATH": "C:/Windows/System32"}, clear=True):
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
        compiler_props = {
            "exe": "/usr/bin/g++-12",
            "compilerType": "gcc",
            "options": "-O2 -std=c++17"
        }
        
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
        compiler_props = {
            "exe": "/usr/bin/clang++-15",
            "compilerType": "clang",
            "options": "-O2 -std=c++20"
        }
        
        env = self.extractor.setup_compiler_environment("clang15", compiler_props)
        
        self.assertEqual(env["CC"], "/usr/bin/clang-15")
        self.assertEqual(env["CXX"], "/usr/bin/clang++-15")
        self.assertEqual(env["CFLAGS"], "-O2 -std=c++20")
        self.assertEqual(env["CXXFLAGS"], "-O2 -std=c++20")
        
    def test_setup_compiler_environment_cpp_compiler(self):
        """Test environment setup for C++ compiler executable on Windows."""
        # Set extractor to Windows platform for this test
        self.extractor.platform = LibraryPlatform.Windows
        
        compiler_props = {
            "exe": "C:/Program Files/Microsoft Visual Studio/VC/bin/cl++.exe",
            "compilerType": "win32-vc"
        }
        
        env = self.extractor.setup_compiler_environment("test_compiler", compiler_props)
        
        self.assertEqual(env["CC"], "C:/Program Files/Microsoft Visual Studio/VC/bin/cl.exe")
        self.assertEqual(env["CXX"], "C:/Program Files/Microsoft Visual Studio/VC/bin/cl++.exe")
        
    def test_setup_compiler_environment_minimal(self):
        """Test environment setup with minimal compiler properties on Linux."""
        compiler_props = {
            "exe": "/usr/bin/gcc",
            "compilerType": "gcc"
        }
        
        env = self.extractor.setup_compiler_environment("test_compiler", compiler_props)
        
        self.assertEqual(env["CC"], "/usr/bin/gcc")
        self.assertEqual(env["CXX"], "/usr/bin/g++")
        self.assertNotIn("INCLUDE", env)
        self.assertNotIn("LIB", env)
        self.assertNotIn("CFLAGS", env)
        self.assertNotIn("CXXFLAGS", env)
        
    @patch('subprocess.run')
    @patch('pathlib.Path.exists')
    def test_extract_cache_for_compiler_success(self, mock_exists, mock_run):
        """Test successful cache extraction for a compiler."""
        mock_exists.return_value = True
        mock_run.return_value = Mock(returncode=0, stdout="Success", stderr="")
        
        compiler_props = {
            "exe": "C:/Program Files/Microsoft Visual Studio/VC/bin/cl.exe",
            "options": "/O2"
        }
        
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            result = self.extractor.extract_cache_for_compiler("test_compiler", compiler_props, output_dir)
            
        self.assertTrue(result)
        self.assertTrue((output_dir / "test_compiler").exists())
        # Should be called twice: once for version check, once for actual extraction
        self.assertEqual(mock_run.call_count, 2)
        
        # Check that PowerShell was called with correct arguments
        call_args = mock_run.call_args
        self.assertEqual(call_args[0][0][0], "pwsh")
        self.assertIn("-OutputDir", call_args[0][0])
        self.assertIn("-ZipOutput:$true", call_args[0][0])
        
    @patch('subprocess.run')
    @patch('pathlib.Path.exists')
    def test_extract_cache_for_compiler_script_not_found(self, mock_exists, mock_run):
        """Test cache extraction when script is not found."""
        mock_exists.return_value = False
        
        compiler_props = {"exe": "C:/compiler/cl.exe"}
        
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            result = self.extractor.extract_cache_for_compiler("test_compiler", compiler_props, output_dir)
            
        self.assertFalse(result)
        mock_run.assert_not_called()
        self.logger.error.assert_called_with(unittest.mock.ANY)
        
    @patch('subprocess.run')
    @patch('pathlib.Path.exists')
    def test_extract_cache_for_compiler_failure(self, mock_exists, mock_run):
        """Test cache extraction failure."""
        mock_exists.return_value = True
        mock_run.return_value = Mock(returncode=1, stdout="", stderr="Error message")
        
        compiler_props = {"exe": "C:/compiler/cl.exe"}
        
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            result = self.extractor.extract_cache_for_compiler("test_compiler", compiler_props, output_dir)
            
        self.assertFalse(result)
        self.logger.error.assert_called()
        
    @patch('subprocess.run')
    @patch('pathlib.Path.exists')
    def test_extract_cache_for_compiler_timeout(self, mock_exists, mock_run):
        """Test cache extraction timeout."""
        mock_exists.return_value = True
        # First call (version check) succeeds, second call (extraction) times out
        mock_run.side_effect = [
            Mock(returncode=0, stdout="PowerShell 7.0.0", stderr=""),  # Version check succeeds
            subprocess.TimeoutExpired("pwsh", 300)  # Extraction times out
        ]
        
        compiler_props = {"exe": "C:/compiler/cl.exe"}
        
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            result = self.extractor.extract_cache_for_compiler("test_compiler", compiler_props, output_dir)
            
        self.assertFalse(result)
        self.logger.error.assert_called_with("Cache extraction timed out for test_compiler")
        
    @patch.object(CompilerCacheExtractor, 'extract_cache_for_compiler')
    @patch.object(CompilerCacheExtractor, 'get_supported_compilers')
    def test_extract_all_compilers_all(self, mock_get_compilers, mock_extract):
        """Test extracting cache for all compilers."""
        mock_compilers = {
            "compiler1": {"exe": "C:/compiler1/cl.exe"},
            "compiler2": {"exe": "C:/compiler2/cl.exe"}
        }
        mock_get_compilers.return_value = mock_compilers
        mock_extract.side_effect = [True, False]  # First succeeds, second fails
        
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            success_count, failed_count = self.extractor.extract_all_compilers(output_dir)
            
        self.assertEqual(success_count, 1)
        self.assertEqual(failed_count, 1)
        self.assertEqual(mock_extract.call_count, 2)
        
    @patch.object(CompilerCacheExtractor, 'extract_cache_for_compiler')
    @patch.object(CompilerCacheExtractor, 'get_supported_compilers')
    def test_extract_all_compilers_filtered(self, mock_get_compilers, mock_extract):
        """Test extracting cache for specific compiler."""
        mock_compilers = {
            "compiler1": {"exe": "C:/compiler1/cl.exe"},
            "compiler2": {"exe": "C:/compiler2/cl.exe"}
        }
        mock_get_compilers.return_value = mock_compilers
        mock_extract.return_value = True
        
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            success_count, failed_count = self.extractor.extract_all_compilers(output_dir, "compiler1")
            
        self.assertEqual(success_count, 1)
        self.assertEqual(failed_count, 0)
        mock_extract.assert_called_once_with("compiler1", {"exe": "C:/compiler1/cl.exe"}, output_dir)
        
    @patch.object(CompilerCacheExtractor, 'get_supported_compilers')
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
        
    @patch('pathlib.Path.exists')
    @patch('lib.compiler_cache.get_properties_compilers_and_libraries')
    def test_full_compiler_discovery_flow(self, mock_get_props, mock_exists):
        """Test the full flow from loading to filtering compilers."""
        mock_exists.return_value = True  # All compilers exist
        
        mock_compilers = {
            "gcc11": {
                "exe": "/usr/bin/g++-11",
                "compilerType": "gcc",
                "options": "-O2"
            },
            "clang15": {
                "exe": "/usr/bin/clang++-15",
                "compilerType": "clang",
                "options": "-O2"
            },
            "msvc_2019_x64": {
                "exe": "C:/Program Files/Microsoft Visual Studio/2019/Professional/VC/Tools/MSVC/14.29.30133/bin/Hostx64/x64/cl.exe",
                "compilerType": "win32-vc",
                "options": "/O2"
            }
        }
        mock_get_props.return_value = [mock_compilers, {}]
        
        extractor = CompilerCacheExtractor(self.logger)  # Defaults to Linux
        supported_compilers = extractor.get_supported_compilers()
        
        # Should include Linux compilers but not MSVC
        self.assertEqual(len(supported_compilers), 2)
        self.assertIn("gcc11", supported_compilers)
        self.assertIn("clang15", supported_compilers)
        self.assertNotIn("msvc_2019_x64", supported_compilers)
        
        # Test environment setup for one of them
        env = extractor.setup_compiler_environment("gcc11", supported_compilers["gcc11"])
        
        self.assertEqual(env["CC"], "/usr/bin/gcc-11")
        self.assertEqual(env["CXX"], "/usr/bin/g++-11")
        self.assertEqual(env["CFLAGS"], "-O2")
        self.assertEqual(env["CXXFLAGS"], "-O2")


if __name__ == '__main__':
    unittest.main()