from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from click.testing import CliRunner
from lib.cli.ce_router import (
    ce_router_healthcheck,
    compilation_path_patterns,
    enable,
    exec_all,
    format_healthcheck,
    get_rule_path_patterns,
    version,
)
from lib.env import Config, Environment


class TestCERouterExecAll(unittest.TestCase):
    def setUp(self):
        self.runner = CliRunner()
        self.cfg = Config(env=Environment.STAGING)

    @patch("lib.cli.ce_router._get_ce_router_instances")
    @patch("lib.cli.ce_router.exec_remote_all")
    @patch("lib.cli.ce_router.are_you_sure")
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

    @patch("lib.cli.ce_router._get_ce_router_instances")
    def test_exec_all_no_instances(self, mock_get_instances):
        mock_get_instances.return_value = []

        result = self.runner.invoke(
            exec_all,
            ["uptime"],
            obj=self.cfg,
        )

        self.assertEqual(result.exit_code, 0)
        self.assertIn("No CE Router instances found", result.output)

    @patch("lib.cli.ce_router._get_ce_router_instances")
    @patch("lib.cli.ce_router.are_you_sure")
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

    @patch("lib.cli.ce_router._get_ce_router_instances")
    @patch("lib.cli.ce_router.exec_remote_all")
    @patch("lib.cli.ce_router.are_you_sure")
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

    @patch("lib.cli.ce_router._get_ce_router_instances")
    @patch("lib.cli.ce_router.exec_remote_all")
    @patch("lib.cli.ce_router.are_you_sure")
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


class TestCompilationPathPatterns(unittest.TestCase):
    def test_prod_patterns_are_unprefixed(self):
        self.assertEqual(
            compilation_path_patterns("prod"),
            ["/api/compiler/*/compile", "/api/compiler/*/cmake", "/api/compiler/*/build/*"],
        )

    def test_non_prod_patterns_are_prefixed(self):
        self.assertEqual(
            compilation_path_patterns("beta"),
            ["/beta/api/compiler/*/compile", "/beta/api/compiler/*/cmake", "/beta/api/compiler/*/build/*"],
        )

    def test_patterns_fit_alb_limits(self):
        for env in ("prod", "staging", "beta"):
            patterns = compilation_path_patterns(env)
            self.assertLessEqual(len(patterns), 5, f"{env} exceeds the ALB match evaluations per rule limit")
            for pattern in patterns:
                self.assertLessEqual(len(pattern), 128, f"{pattern} exceeds the ALB path pattern length limit")

    def test_get_rule_path_patterns(self):
        rule = {
            "Conditions": [
                {"Field": "host-header", "Values": ["godbolt.org"]},
                {"Field": "path-pattern", "Values": ["/api/compiler/*/compile", "/api/compiler/*/cmake"]},
            ]
        }
        self.assertEqual(get_rule_path_patterns(rule), ["/api/compiler/*/compile", "/api/compiler/*/cmake"])

    def test_get_rule_path_patterns_without_conditions(self):
        self.assertEqual(get_rule_path_patterns({}), [])


class TestCERouterEnable(unittest.TestCase):
    def setUp(self):
        self.runner = CliRunner()
        self.cfg = Config(env=Environment.PROD)
        self.alb_client = MagicMock()

    def _invoke(self, rule_conditions):
        rule = {"RuleArn": "rule-arn", "Priority": "70", "Conditions": rule_conditions}
        with (
            patch("lib.cli.ce_router._get_alb_client", return_value=self.alb_client),
            patch(
                "lib.cli.ce_router._find_ce_router_target_groups",
                return_value={"prod": {"arn": "tg-arn", "name": "ce-router-prod"}},
            ),
            patch("lib.cli.ce_router._find_compiler_explorer_listener", return_value="listener-arn"),
            patch("lib.cli.ce_router._find_or_create_ce_router_rules", return_value={"prod": rule}),
        ):
            return self.runner.invoke(enable, ["-e", "prod", "--skip-confirmation"], obj=self.cfg)

    def test_enable_sets_all_patterns(self):
        result = self._invoke([{"Field": "path-pattern", "Values": ["/killswitch-disabled-prod-*"]}])

        self.assertEqual(result.exit_code, 0)
        self.alb_client.modify_rule.assert_called_once_with(
            RuleArn="rule-arn",
            Conditions=[
                {
                    "Field": "path-pattern",
                    "Values": ["/api/compiler/*/compile", "/api/compiler/*/cmake", "/api/compiler/*/build/*"],
                }
            ],
        )

    def test_enable_updates_rule_missing_build_pattern(self):
        result = self._invoke([
            {"Field": "path-pattern", "Values": ["/api/compiler/*/compile", "/api/compiler/*/cmake"]}
        ])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("Updating ce-router ALB path patterns", result.output)
        self.alb_client.modify_rule.assert_called_once()

    def test_enable_leaves_up_to_date_rule_alone(self):
        result = self._invoke([{"Field": "path-pattern", "Values": compilation_path_patterns("prod")}])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("already enabled", result.output)
        self.alb_client.modify_rule.assert_not_called()


class TestCERouterVersion(unittest.TestCase):
    def setUp(self):
        self.runner = CliRunner()
        self.cfg = Config(env=Environment.STAGING)

    @patch("lib.cli.ce_router._get_ce_router_instances")
    @patch("lib.cli.ce_router.exec_remote")
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

    @patch("lib.cli.ce_router._get_ce_router_instances")
    def test_version_no_instances(self, mock_get_instances):
        mock_get_instances.return_value = []

        result = self.runner.invoke(
            version,
            obj=self.cfg,
        )

        self.assertEqual(result.exit_code, 0)
        self.assertIn("No CE Router instances found", result.output)

    @patch("lib.cli.ce_router._get_ce_router_instances")
    @patch("lib.cli.ce_router.exec_remote")
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

    @patch("lib.cli.ce_router._get_ce_router_instances")
    @patch("lib.cli.ce_router.exec_remote")
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

    @patch("lib.cli.ce_router._get_ce_router_instances")
    @patch("lib.cli.ce_router.exec_remote")
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


class TestFormatHealthcheck(unittest.TestCase):
    """The router answers JSON, and a 200 does not by itself mean it can route."""

    def test_healthy_with_connected_websocket(self):
        body = '{"status": "healthy", "websocket": "connected"}'

        self.assertIn("HEALTHY", format_healthcheck(body))
        self.assertNotIn("websocket", format_healthcheck(body))

    def test_healthy_with_disconnected_websocket_is_called_out(self):
        body = '{"status": "healthy", "websocket": "disconnected"}'

        result = format_healthcheck(body)

        self.assertIn("HEALTHY", result)
        self.assertIn("disconnected", result)

    def test_unhealthy_reports_the_reason(self):
        body = '{"status": "unhealthy", "reason": "WebSocket connection failed"}'

        result = format_healthcheck(body)

        self.assertIn("UNHEALTHY", result)
        self.assertIn("WebSocket connection failed", result)

    def test_non_json_response(self):
        result = format_healthcheck("<html>502 Bad Gateway</html>")

        self.assertIn("UNHEALTHY", result)
        self.assertIn("502", result)

    def test_empty_response(self):
        result = format_healthcheck("")

        self.assertIn("UNHEALTHY", result)
        self.assertIn("(empty)", result)


class TestCERouterHealthcheck(unittest.TestCase):
    def setUp(self):
        self.runner = CliRunner()
        self.cfg = Config(env=Environment.STAGING)

    def _instance(self, state="running", instance_id="i-12345", ip="10.0.1.100"):
        instance = MagicMock()
        instance.instance.id = instance_id
        instance.instance.private_ip_address = ip
        instance.instance.state = {"Name": state}
        instance.__str__ = MagicMock(return_value=f"{instance_id}@{ip}")
        return instance

    @patch("lib.cli.ce_router._get_ce_router_instances")
    @patch("lib.cli.ce_router.exec_remote")
    def test_healthcheck_queries_each_instance(self, mock_exec_remote, mock_get_instances):
        mock_get_instances.return_value = [self._instance()]
        mock_exec_remote.return_value = '{"status": "healthy", "websocket": "connected"}'

        result = self.runner.invoke(ce_router_healthcheck, obj=self.cfg)

        self.assertEqual(result.exit_code, 0)
        self.assertIn("i-12345@10.0.1.100", result.output)
        self.assertIn("HEALTHY", result.output)
        # exec_remote needs the instance wrapper, not its id: passing the id raised
        # AttributeError in ssh_address_for and the command never worked.
        called_with = mock_exec_remote.call_args[0][0]
        self.assertEqual(called_with, mock_get_instances.return_value[0])
        self.assertEqual(mock_exec_remote.call_args[0][1], ["curl", "-s", "http://10.0.1.100/healthcheck"])

    @patch("lib.cli.ce_router._get_ce_router_instances")
    @patch("lib.cli.ce_router.exec_remote")
    def test_healthcheck_skips_instances_that_are_not_running(self, mock_exec_remote, mock_get_instances):
        mock_get_instances.return_value = [self._instance(state="stopped")]

        result = self.runner.invoke(ce_router_healthcheck, obj=self.cfg)

        self.assertEqual(result.exit_code, 0)
        self.assertIn("SKIPPED", result.output)
        mock_exec_remote.assert_not_called()

    @patch("lib.cli.ce_router._get_ce_router_instances")
    @patch("lib.cli.ce_router.exec_remote")
    def test_healthcheck_reports_an_unreachable_instance(self, mock_exec_remote, mock_get_instances):
        mock_get_instances.return_value = [self._instance()]
        mock_exec_remote.side_effect = RuntimeError("ssh failed")

        result = self.runner.invoke(ce_router_healthcheck, obj=self.cfg)

        self.assertEqual(result.exit_code, 0)
        self.assertIn("ERROR", result.output)

    @patch("lib.cli.ce_router._get_ce_router_instances")
    def test_healthcheck_no_instances(self, mock_get_instances):
        mock_get_instances.return_value = []

        result = self.runner.invoke(ce_router_healthcheck, obj=self.cfg)

        self.assertEqual(result.exit_code, 0)
        self.assertIn("No CE Router instances found", result.output)
