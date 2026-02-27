"""Tests for discovery status display and dynamic menu in blue-green deployments."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import lib.cli  # noqa: F401 (must import before blue_green_deploy to avoid circular import)
from lib.blue_green_deploy import BlueGreenDeployment, DeploymentCancelledException
from lib.env import Config, Environment


class TestDisplayDiscoveryStatus(unittest.TestCase):
    """Tests for _display_discovery_status."""

    @patch("lib.blue_green_deploy.discovery_exists")
    @patch("builtins.print")
    def test_all_found(self, mock_print, mock_exists):
        mock_exists.return_value = True
        BlueGreenDeployment._display_discovery_status("gh-123")
        calls = [call[0][0] for call in mock_print.call_args_list]
        assert any("prod:" in c and "found" in c for c in calls)
        assert any("staging:" in c and "found" in c for c in calls)
        assert any("beta:" in c and "found" in c for c in calls)
        # "not found" should NOT appear
        assert not any("not found" in c for c in calls)

    @patch("lib.blue_green_deploy.discovery_exists")
    @patch("builtins.print")
    def test_none_found(self, mock_print, mock_exists):
        mock_exists.return_value = False
        BlueGreenDeployment._display_discovery_status("gh-456")
        calls = [call[0][0] for call in mock_print.call_args_list]
        assert all("not found" in c for c in calls if ":" in c and "status" not in c.lower())

    @patch("lib.blue_green_deploy.discovery_exists")
    @patch("builtins.print")
    def test_mixed_status(self, mock_print, mock_exists):
        mock_exists.side_effect = lambda env, _ver: env == "staging"
        BlueGreenDeployment._display_discovery_status("gh-789")
        calls = [call[0][0] for call in mock_print.call_args_list]
        # prod: not found, staging: found, beta: not found
        prod_line = next(c for c in calls if "prod:" in c)
        staging_line = next(c for c in calls if "staging:" in c)
        beta_line = next(c for c in calls if "beta:" in c)
        assert "not found" in prod_line
        assert "found" in staging_line and "not found" not in staging_line
        assert "not found" in beta_line


class TestHandleProdMissingDiscovery(unittest.TestCase):
    """Tests for _handle_prod_missing_discovery."""

    def _make_deployment(self):
        with patch("lib.blue_green_deploy.ssm_client"), patch("lib.blue_green_deploy.is_running_on_admin_node"):
            cfg = Config(env=Environment.PROD)
            return BlueGreenDeployment(cfg)

    @patch("lib.blue_green_deploy.get_release_without_discovery_check")
    @patch("lib.blue_green_deploy.copy_discovery_to_prod")
    @patch("lib.blue_green_deploy.check_compiler_discovery")
    @patch("lib.blue_green_deploy.discovery_exists")
    @patch("builtins.input", return_value="1")
    @patch("builtins.print")
    def test_staging_available_copy_succeeds(
        self, mock_print, _mock_input, mock_exists, mock_check, mock_copy, _mock_get
    ):
        """When staging has discovery and user picks copy, should copy from staging."""
        mock_exists.side_effect = lambda env, _ver: env == "staging"
        mock_copy.return_value = True
        mock_check.return_value = MagicMock()
        deploy = self._make_deployment()

        result = deploy._handle_prod_missing_discovery(RuntimeError("no discovery"), "gh-123", None)

        assert result is not None
        mock_copy.assert_called_once_with("staging", "gh-123")
        calls = [call[0][0] for call in mock_print.call_args_list]
        assert any("Staging discovery IS available" in c for c in calls)
        assert any("Copy discovery from staging (recommended)" in c for c in calls)

    @patch("lib.blue_green_deploy.get_release_without_discovery_check")
    @patch("lib.blue_green_deploy.copy_discovery_to_prod")
    @patch("lib.blue_green_deploy.check_compiler_discovery")
    @patch("lib.blue_green_deploy.discovery_exists")
    @patch("builtins.input", return_value="1")
    @patch("builtins.print")
    def test_beta_available_copy(self, mock_print, _mock_input, mock_exists, mock_check, mock_copy, mock_get):
        """When only beta has discovery and user picks copy, should copy from beta."""
        mock_exists.side_effect = lambda env, _ver: env == "beta"
        mock_copy.return_value = True
        mock_check.return_value = MagicMock()
        mock_get.return_value = MagicMock()
        deploy = self._make_deployment()

        deploy._handle_prod_missing_discovery(RuntimeError("no discovery"), "gh-123", None)

        mock_copy.assert_called_once_with("beta", "gh-123")
        calls = [call[0][0] for call in mock_print.call_args_list]
        assert any("Beta discovery IS available" in c for c in calls)
        assert any("Copy discovery from beta" in c for c in calls)

    @patch("lib.blue_green_deploy.get_release_without_discovery_check")
    @patch("lib.blue_green_deploy.discovery_exists")
    @patch("builtins.input", return_value="1")
    @patch("builtins.print")
    def test_neither_available_continue(self, mock_print, _mock_input, mock_exists, mock_get):
        """When neither staging nor beta has discovery, option 1 is continue without discovery."""
        mock_exists.return_value = False
        mock_get.return_value = MagicMock()
        deploy = self._make_deployment()

        deploy._handle_prod_missing_discovery(RuntimeError("no discovery"), "gh-123", None)

        mock_get.assert_called_once()
        calls = [call[0][0] for call in mock_print.call_args_list]
        assert any("WARNING: No discovery found in staging or beta" in c for c in calls)
        assert any("ce workflows run-discovery" in c for c in calls)
        assert any("Continue without discovery (risky)" in c for c in calls)

    @patch("lib.blue_green_deploy.discovery_exists")
    @patch("builtins.input", return_value="2")
    @patch("builtins.print")
    def test_neither_available_cancel(self, _mock_print, _mock_input, mock_exists):
        """When neither has discovery and user picks cancel, raises DeploymentCancelledException."""
        mock_exists.return_value = False
        deploy = self._make_deployment()

        with self.assertRaises(DeploymentCancelledException):
            deploy._handle_prod_missing_discovery(RuntimeError("no discovery"), "gh-123", None)

    @patch("lib.blue_green_deploy.discovery_exists")
    @patch("builtins.input", return_value="3")
    @patch("builtins.print")
    def test_staging_available_cancel(self, _mock_print, _mock_input, mock_exists):
        """When staging has discovery but user cancels, raises DeploymentCancelledException."""
        mock_exists.side_effect = lambda env, _ver: env == "staging"
        deploy = self._make_deployment()

        with self.assertRaises(DeploymentCancelledException):
            deploy._handle_prod_missing_discovery(RuntimeError("no discovery"), "gh-123", None)

    @patch("lib.blue_green_deploy.get_release_without_discovery_check")
    @patch("lib.blue_green_deploy.discovery_exists")
    @patch("builtins.input", return_value="2")
    @patch("builtins.print")
    def test_staging_available_continue_without(self, _mock_print, _mock_input, mock_exists, mock_get):
        """When staging has discovery but user picks continue without, should skip copy."""
        mock_exists.side_effect = lambda env, _ver: env == "staging"
        mock_get.return_value = MagicMock()
        deploy = self._make_deployment()

        deploy._handle_prod_missing_discovery(RuntimeError("no discovery"), "gh-123", None)

        mock_get.assert_called_once()

    @patch("lib.blue_green_deploy.get_release_without_discovery_check")
    @patch("lib.blue_green_deploy.discovery_exists")
    @patch("builtins.input", side_effect=["9", "1"])
    @patch("builtins.print")
    def test_neither_available_invalid_then_valid(self, _mock_print, _mock_input, mock_exists, mock_get):
        """Invalid input is rejected, then valid input is accepted."""
        mock_exists.return_value = False
        mock_get.return_value = MagicMock()
        deploy = self._make_deployment()

        deploy._handle_prod_missing_discovery(RuntimeError("no discovery"), "gh-123", None)

        mock_get.assert_called_once()


class TestCopyAndCheckDiscovery(unittest.TestCase):
    """Tests for _copy_and_check_discovery."""

    def _make_deployment(self):
        with patch("lib.blue_green_deploy.ssm_client"), patch("lib.blue_green_deploy.is_running_on_admin_node"):
            cfg = Config(env=Environment.PROD)
            return BlueGreenDeployment(cfg)

    @patch("lib.blue_green_deploy.check_compiler_discovery")
    @patch("lib.blue_green_deploy.copy_discovery_to_prod")
    @patch("builtins.print")
    def test_copy_success_check_passes(self, _mock_print, mock_copy, mock_check):
        """Copy succeeds and re-check passes: returns release from check."""
        mock_copy.return_value = True
        expected_release = MagicMock()
        mock_check.return_value = expected_release
        deploy = self._make_deployment()

        result = deploy._copy_and_check_discovery("staging", "gh-123", None)

        assert result is expected_release

    @patch("lib.blue_green_deploy.get_release_without_discovery_check")
    @patch("lib.blue_green_deploy.check_compiler_discovery")
    @patch("lib.blue_green_deploy.copy_discovery_to_prod")
    @patch("builtins.print")
    def test_copy_success_check_fails(self, _mock_print, mock_copy, mock_check, mock_get):
        """Copy succeeds but re-check fails: falls back to get_release_without_discovery_check."""
        mock_copy.return_value = True
        mock_check.side_effect = RuntimeError("still no discovery")
        expected_release = MagicMock()
        mock_get.return_value = expected_release
        deploy = self._make_deployment()

        result = deploy._copy_and_check_discovery("staging", "gh-123", None)

        assert result is expected_release

    @patch("lib.blue_green_deploy.get_release_without_discovery_check")
    @patch("lib.blue_green_deploy.copy_discovery_to_prod")
    @patch("builtins.print")
    def test_copy_returns_false(self, _mock_print, mock_copy, mock_get):
        """copy_discovery_to_prod returns False: falls back to get_release_without_discovery_check."""
        mock_copy.return_value = False
        expected_release = MagicMock()
        mock_get.return_value = expected_release
        deploy = self._make_deployment()

        result = deploy._copy_and_check_discovery("beta", "gh-123", None)

        assert result is expected_release


if __name__ == "__main__":
    unittest.main()
