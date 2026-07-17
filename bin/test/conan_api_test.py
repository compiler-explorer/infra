from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock, patch

from lib.conan_api import (
    clear_build_status_for_compiler,
    clear_build_status_for_library,
    get_conan_auth_token,
    list_failed_builds,
)


class TestGetConanAuthToken(unittest.TestCase):
    @patch("lib.conan_api.requests.post")
    @patch.dict("os.environ", {"CONAN_PASSWORD": "test-password"})
    def test_login_with_env_var(self, mock_post):
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.content = json.dumps({"token": "abc123"}).encode()
        mock_post.return_value = mock_response

        token = get_conan_auth_token()

        self.assertEqual(token, "abc123")
        call_kwargs = mock_post.call_args
        self.assertEqual(call_kwargs[1]["json"]["password"], "test-password")

    @patch("lib.conan_api.get_ssm_param")
    @patch("lib.conan_api.requests.post")
    @patch.dict("os.environ", {}, clear=True)
    def test_login_with_ssm_fallback(self, mock_post, mock_ssm):
        mock_ssm.return_value = "ssm-password"
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.content = json.dumps({"token": "xyz789"}).encode()
        mock_post.return_value = mock_response

        token = get_conan_auth_token()

        self.assertEqual(token, "xyz789")
        mock_ssm.assert_called_once_with("/compiler-explorer/conanpwd")

    @patch("lib.conan_api.requests.post")
    @patch.dict("os.environ", {"CONAN_PASSWORD": "test-password"})
    def test_login_failure(self, mock_post):
        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.status_code = 403
        mock_response.text = "Forbidden"
        mock_post.return_value = mock_response

        with self.assertRaises(RuntimeError, msg="Conan proxy login failed"):
            get_conan_auth_token()


class TestClearBuildStatusForCompiler(unittest.TestCase):
    @patch("lib.conan_api.get_conan_auth_token")
    @patch("lib.conan_api.requests.post")
    def test_success(self, mock_post, mock_auth):
        mock_auth.return_value = "token123"
        mock_response = MagicMock()
        mock_response.ok = True
        mock_post.return_value = mock_response

        clear_build_status_for_compiler("gcc", "g141")

        call_kwargs = mock_post.call_args
        self.assertEqual(call_kwargs[1]["json"], {"compiler": "gcc", "compiler_version": "g141"})
        self.assertIn("Bearer token123", call_kwargs[1]["headers"]["Authorization"])

    @patch("lib.conan_api.get_conan_auth_token")
    @patch("lib.conan_api.requests.post")
    def test_post_failure(self, mock_post, mock_auth):
        mock_auth.return_value = "token123"
        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_post.return_value = mock_response

        with self.assertRaises(RuntimeError, msg="Failed to clear build status"):
            clear_build_status_for_compiler("gcc", "g141")


class TestClearBuildStatusForLibrary(unittest.TestCase):
    @patch("lib.conan_api.get_conan_auth_token")
    @patch("lib.conan_api.requests.post")
    def test_clear_all_versions(self, mock_post, mock_auth):
        mock_auth.return_value = "token123"
        mock_response = MagicMock()
        mock_response.ok = True
        mock_post.return_value = mock_response

        clear_build_status_for_library("fmt")

        call_kwargs = mock_post.call_args
        self.assertEqual(call_kwargs[1]["json"], {"library": "fmt"})

    @patch("lib.conan_api.get_conan_auth_token")
    @patch("lib.conan_api.requests.post")
    def test_clear_specific_version(self, mock_post, mock_auth):
        mock_auth.return_value = "token123"
        mock_response = MagicMock()
        mock_response.ok = True
        mock_post.return_value = mock_response

        clear_build_status_for_library("fmt", "10.0.0")

        call_kwargs = mock_post.call_args
        self.assertEqual(call_kwargs[1]["json"], {"library": "fmt", "library_version": "10.0.0"})

    @patch("lib.conan_api.get_conan_auth_token")
    @patch("lib.conan_api.requests.post")
    def test_post_failure(self, mock_post, mock_auth):
        mock_auth.return_value = "token123"
        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_post.return_value = mock_response

        with self.assertRaises(RuntimeError, msg="Failed to clear build status"):
            clear_build_status_for_library("fmt")


class TestListFailedBuilds(unittest.TestCase):
    @patch("lib.conan_api.requests.get")
    def test_success(self, mock_get):
        builds = [
            {
                "library": "fmt",
                "library_version": "10.0.0",
                "compiler": "gcc",
                "compiler_version": "g141",
                "arch": "x86_64",
                "libcxx": "libstdc++",
                "success": False,
                "build_dt": "2026-03-01",
            }
        ]
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.content = json.dumps(builds).encode()
        mock_get.return_value = mock_response

        result = list_failed_builds()

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["library"], "fmt")

    @patch("lib.conan_api.requests.get")
    def test_empty_list(self, mock_get):
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.content = json.dumps([]).encode()
        mock_get.return_value = mock_response

        result = list_failed_builds()

        self.assertEqual(result, [])

    @patch("lib.conan_api.requests.get")
    def test_fetch_failure(self, mock_get):
        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_get.return_value = mock_response

        with self.assertRaises(RuntimeError, msg="Failed to fetch failed builds"):
            list_failed_builds()
