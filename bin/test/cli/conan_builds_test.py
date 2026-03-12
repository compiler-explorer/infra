from __future__ import annotations

import unittest
from unittest.mock import patch

from click.testing import CliRunner
from lib.cli.conan_builds import build_status


class TestClearForCompiler(unittest.TestCase):
    def setUp(self):
        self.runner = CliRunner()

    @patch("lib.cli.conan_builds.clear_build_status_for_compiler")
    def test_clear_gcc(self, mock_clear):
        result = self.runner.invoke(build_status, ["clear-for-compiler", "g141"])
        self.assertEqual(result.exit_code, 0)
        mock_clear.assert_called_once_with("gcc", "g141")
        self.assertIn("Done", result.output)

    @patch("lib.cli.conan_builds.clear_build_status_for_compiler")
    def test_clear_clang(self, mock_clear):
        result = self.runner.invoke(build_status, ["clear-for-compiler", "clang1400"])
        self.assertEqual(result.exit_code, 0)
        mock_clear.assert_called_once_with("clang", "clang1400")

    def test_unknown_compiler_family(self):
        result = self.runner.invoke(build_status, ["clear-for-compiler", "msvc19"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("Cannot infer compiler family", result.output)

    @patch("lib.cli.conan_builds.clear_build_status_for_compiler")
    def test_api_error(self, mock_clear):
        mock_clear.side_effect = RuntimeError("Connection refused")
        result = self.runner.invoke(build_status, ["clear-for-compiler", "g141"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("Connection refused", result.output)


class TestClearForLibrary(unittest.TestCase):
    def setUp(self):
        self.runner = CliRunner()

    @patch("lib.cli.conan_builds.clear_build_status_for_library")
    def test_clear_all_versions(self, mock_clear):
        result = self.runner.invoke(build_status, ["clear-for-library", "fmt"])
        self.assertEqual(result.exit_code, 0)
        mock_clear.assert_called_once_with("fmt", None)
        self.assertIn("Done", result.output)

    @patch("lib.cli.conan_builds.clear_build_status_for_library")
    def test_clear_specific_version(self, mock_clear):
        result = self.runner.invoke(build_status, ["clear-for-library", "fmt", "--version", "10.0.0"])
        self.assertEqual(result.exit_code, 0)
        mock_clear.assert_called_once_with("fmt", "10.0.0")
        self.assertIn("version 10.0.0", result.output)

    @patch("lib.cli.conan_builds.clear_build_status_for_library")
    def test_api_error(self, mock_clear):
        mock_clear.side_effect = RuntimeError("Connection refused")
        result = self.runner.invoke(build_status, ["clear-for-library", "fmt"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("Connection refused", result.output)


class TestListFailed(unittest.TestCase):
    def setUp(self):
        self.runner = CliRunner()

    def test_no_filter_rejected(self):
        result = self.runner.invoke(build_status, ["list-failed"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("Specify at least one of", result.output)

    @patch("lib.cli.conan_builds.list_failed_builds")
    def test_list_failed_builds_filters_successes(self, mock_list):
        mock_list.return_value = [
            {
                "library": "fmt",
                "library_version": "10.0.0",
                "compiler_version": "g141",
                "arch": "x86_64",
                "libcxx": "libstdc++",
                "success": False,
                "build_dt": "2026-03-01",
            },
            {
                "library": "catch2",
                "library_version": "3.0.0",
                "compiler_version": "g141",
                "arch": "x86_64",
                "libcxx": "libstdc++",
                "success": True,
                "build_dt": "2026-03-01",
            },
        ]
        result = self.runner.invoke(build_status, ["list-failed", "--compiler-version", "g141"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("fmt", result.output)
        self.assertNotIn("catch2", result.output)
        self.assertIn("Total: 1 failed build(s)", result.output)

    @patch("lib.cli.conan_builds.list_failed_builds")
    def test_filter_by_library(self, mock_list):
        mock_list.return_value = [
            {"library": "fmt", "library_version": "10.0.0", "compiler_version": "g141", "success": False},
            {"library": "boost", "library_version": "1.85.0", "compiler_version": "g141", "success": False},
        ]
        result = self.runner.invoke(build_status, ["list-failed", "--library", "fmt"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("fmt", result.output)
        self.assertNotIn("boost", result.output)

    @patch("lib.cli.conan_builds.list_failed_builds")
    def test_filter_by_compiler_version(self, mock_list):
        mock_list.return_value = [
            {"library": "fmt", "library_version": "10.0.0", "compiler_version": "g141", "success": False},
            {"library": "fmt", "library_version": "10.0.0", "compiler_version": "clang1400", "success": False},
        ]
        result = self.runner.invoke(build_status, ["list-failed", "--compiler-version", "g141"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("g141", result.output)
        self.assertNotIn("clang1400", result.output)

    @patch("lib.cli.conan_builds.list_failed_builds")
    def test_no_failed_builds(self, mock_list):
        mock_list.return_value = []
        result = self.runner.invoke(build_status, ["list-failed", "--library", "fmt"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("No failed builds found", result.output)

    @patch("lib.cli.conan_builds.list_failed_builds")
    def test_api_error(self, mock_list):
        mock_list.side_effect = RuntimeError("Connection refused")
        result = self.runner.invoke(build_status, ["list-failed", "--library", "fmt"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("Connection refused", result.output)
