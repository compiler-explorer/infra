from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from click.testing import CliRunner
from lib.cli.ce_router_killswitch import exec_all, version
from lib.env import Config, Environment


class TestCERouterExecAll(unittest.TestCase):
    def setUp(self):
        self.runner = CliRunner()
        self.cfg = Config(env=Environment.STAGING)

    @patch("lib.cli.ce_router_killswitch._get_ce_router_instances")
    @patch("lib.cli.ce_router_killswitch.exec_remote_all")
    @patch("lib.cli.ce_router_killswitch.are_you_sure")
    def test_exec_all_success(self, mock_are_you_sure, mock_exec_remote_all, mock_get_instances):
        mock_instance = MagicMock()
        mock_instance.instance.id = "i-12345"
        mock_instance.instance.private_ip_address = "10.0.1.100"
        mock_get_instances.return_value = [mock_instance]
        mock_are_you_sure.return_value = True

        result = self.runner.invoke(
            exec_all,
            ["uptime"],
            obj=self.cfg,
        )

        self.assertEqual(result.exit_code, 0)
        self.assertIn("Running 'uptime' on 1 CE Router instances", result.output)
        mock_exec_remote_all.assert_called_once_with([mock_instance], ("uptime",))

    @patch("lib.cli.ce_router_killswitch._get_ce_router_instances")
    def test_exec_all_no_instances(self, mock_get_instances):
        mock_get_instances.return_value = []

        result = self.runner.invoke(
            exec_all,
            ["uptime"],
            obj=self.cfg,
        )

        self.assertEqual(result.exit_code, 0)
        self.assertIn("No CE Router instances found", result.output)

    @patch("lib.cli.ce_router_killswitch._get_ce_router_instances")
    @patch("lib.cli.ce_router_killswitch.are_you_sure")
    def test_exec_all_user_cancels(self, mock_are_you_sure, mock_get_instances):
        mock_instance = MagicMock()
        mock_get_instances.return_value = [mock_instance]
        mock_are_you_sure.return_value = False

        result = self.runner.invoke(
            exec_all,
            ["uptime"],
            obj=self.cfg,
        )

        self.assertEqual(result.exit_code, 0)
        self.assertNotIn("Running", result.output)

    @patch("lib.cli.ce_router_killswitch._get_ce_router_instances")
    @patch("lib.cli.ce_router_killswitch.exec_remote_all")
    @patch("lib.cli.ce_router_killswitch.are_you_sure")
    def test_exec_all_with_multiple_args(self, mock_are_you_sure, mock_exec_remote_all, mock_get_instances):
        mock_instance = MagicMock()
        mock_get_instances.return_value = [mock_instance]
        mock_are_you_sure.return_value = True

        result = self.runner.invoke(
            exec_all,
            ["sudo", "systemctl", "status", "ce-router"],
            obj=self.cfg,
        )

        self.assertEqual(result.exit_code, 0)
        self.assertIn("sudo systemctl status ce-router", result.output)
        mock_exec_remote_all.assert_called_once_with([mock_instance], ("sudo", "systemctl", "status", "ce-router"))

    @patch("lib.cli.ce_router_killswitch._get_ce_router_instances")
    @patch("lib.cli.ce_router_killswitch.exec_remote_all")
    @patch("lib.cli.ce_router_killswitch.are_you_sure")
    def test_exec_all_with_multiple_instances(self, mock_are_you_sure, mock_exec_remote_all, mock_get_instances):
        mock_instance1 = MagicMock()
        mock_instance1.instance.id = "i-12345"
        mock_instance1.instance.private_ip_address = "10.0.1.100"
        mock_instance2 = MagicMock()
        mock_instance2.instance.id = "i-67890"
        mock_instance2.instance.private_ip_address = "10.0.1.101"
        mock_get_instances.return_value = [mock_instance1, mock_instance2]
        mock_are_you_sure.return_value = True

        result = self.runner.invoke(
            exec_all,
            ["uptime"],
            obj=self.cfg,
        )

        self.assertEqual(result.exit_code, 0)
        self.assertIn("Running 'uptime' on 2 CE Router instances", result.output)
        mock_exec_remote_all.assert_called_once_with([mock_instance1, mock_instance2], ("uptime",))


class TestCERouterVersion(unittest.TestCase):
    def setUp(self):
        self.runner = CliRunner()
        self.cfg = Config(env=Environment.STAGING)

    @patch("lib.cli.ce_router_killswitch._get_ce_router_instances")
    @patch("lib.cli.ce_router_killswitch.exec_remote")
    def test_version_success(self, mock_exec_remote, mock_get_instances):
        mock_instance = MagicMock()
        mock_instance.instance.id = "i-12345"
        mock_instance.instance.private_ip_address = "10.0.1.100"
        mock_instance.__str__ = MagicMock(return_value="i-12345@10.0.1.100")
        mock_get_instances.return_value = [mock_instance]
        mock_exec_remote.return_value = "v1.2.3\n"

        result = self.runner.invoke(
            version,
            obj=self.cfg,
        )

        self.assertEqual(result.exit_code, 0)
        self.assertIn("CE Router versions for STAGING", result.output)
        self.assertIn("i-12345@10.0.1.100: v1.2.3", result.output)
        mock_exec_remote.assert_called_once_with(
            mock_instance, ["cat", "/infra/.deploy/ce-router-version"], ignore_errors=True
        )

    @patch("lib.cli.ce_router_killswitch._get_ce_router_instances")
    def test_version_no_instances(self, mock_get_instances):
        mock_get_instances.return_value = []

        result = self.runner.invoke(
            version,
            obj=self.cfg,
        )

        self.assertEqual(result.exit_code, 0)
        self.assertIn("No CE Router instances found", result.output)

    @patch("lib.cli.ce_router_killswitch._get_ce_router_instances")
    @patch("lib.cli.ce_router_killswitch.exec_remote")
    def test_version_multiple_instances(self, mock_exec_remote, mock_get_instances):
        mock_instance1 = MagicMock()
        mock_instance1.instance.id = "i-12345"
        mock_instance1.instance.private_ip_address = "10.0.1.100"
        mock_instance1.__str__ = MagicMock(return_value="i-12345@10.0.1.100")
        mock_instance2 = MagicMock()
        mock_instance2.instance.id = "i-67890"
        mock_instance2.instance.private_ip_address = "10.0.1.101"
        mock_instance2.__str__ = MagicMock(return_value="i-67890@10.0.1.101")
        mock_get_instances.return_value = [mock_instance1, mock_instance2]
        mock_exec_remote.side_effect = ["v1.2.3\n", "v1.2.4\n"]

        result = self.runner.invoke(
            version,
            obj=self.cfg,
        )

        self.assertEqual(result.exit_code, 0)
        self.assertIn("CE Router versions for STAGING", result.output)
        self.assertIn("i-12345@10.0.1.100: v1.2.3", result.output)
        self.assertIn("i-67890@10.0.1.101: v1.2.4", result.output)

    @patch("lib.cli.ce_router_killswitch._get_ce_router_instances")
    @patch("lib.cli.ce_router_killswitch.exec_remote")
    def test_version_error_reading(self, mock_exec_remote, mock_get_instances):
        mock_instance = MagicMock()
        mock_instance.instance.id = "i-12345"
        mock_instance.instance.private_ip_address = "10.0.1.100"
        mock_instance.__str__ = MagicMock(return_value="i-12345@10.0.1.100")
        mock_get_instances.return_value = [mock_instance]
        mock_exec_remote.side_effect = RuntimeError("Connection failed")

        result = self.runner.invoke(
            version,
            obj=self.cfg,
        )

        self.assertEqual(result.exit_code, 0)
        self.assertIn("CE Router versions for STAGING", result.output)
        self.assertIn("i-12345@10.0.1.100: error reading version", result.output)

    @patch("lib.cli.ce_router_killswitch._get_ce_router_instances")
    @patch("lib.cli.ce_router_killswitch.exec_remote")
    def test_version_empty_file(self, mock_exec_remote, mock_get_instances):
        mock_instance = MagicMock()
        mock_instance.instance.id = "i-12345"
        mock_instance.instance.private_ip_address = "10.0.1.100"
        mock_instance.__str__ = MagicMock(return_value="i-12345@10.0.1.100")
        mock_get_instances.return_value = [mock_instance]
        mock_exec_remote.return_value = ""

        result = self.runner.invoke(
            version,
            obj=self.cfg,
        )

        self.assertEqual(result.exit_code, 0)
        self.assertIn("CE Router versions for STAGING", result.output)
        self.assertIn("i-12345@10.0.1.100: unknown", result.output)
