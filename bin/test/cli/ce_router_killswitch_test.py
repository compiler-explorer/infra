from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from click.testing import CliRunner
from lib.cli.ce_router_killswitch import (
    compilation_path_patterns,
    disable,
    enable,
    exec_all,
    get_rule_path_patterns,
    rule_conditions_with_paths,
    version,
)
from lib.env import Config, Environment

ORIGIN_CONDITION = {
    "Field": "http-header",
    "HttpHeaderConfig": {"HttpHeaderName": "X-CE-Origin-Verify", "Values": ["secret"]},
}


class TestRuleConditionsWithPaths(unittest.TestCase):
    @patch("lib.cli.ce_router_killswitch._origin_verify_condition", return_value=ORIGIN_CONDITION)
    def test_adds_origin_header_when_rule_lacks_it(self, origin_condition):
        rule = {"Conditions": [{"Field": "path-pattern", "Values": ["/old"]}]}
        self.assertEqual(
            rule_conditions_with_paths(rule, ["/new"]),
            [{"Field": "path-pattern", "Values": ["/new"]}, ORIGIN_CONDITION],
        )
        origin_condition.assert_called_once()

    @patch("lib.cli.ce_router_killswitch._origin_verify_condition")
    def test_keeps_existing_origin_header_without_consulting_ssm(self, origin_condition):
        existing = {
            "Field": "http-header",
            "Values": [],
            "HttpHeaderConfig": {"HttpHeaderName": "x-ce-origin-verify", "Values": ["live-secret"]},
        }
        rule = {"Conditions": [{"Field": "path-pattern", "Values": ["/old"]}, existing]}
        self.assertEqual(
            rule_conditions_with_paths(rule, ["/new"]),
            [
                {"Field": "path-pattern", "Values": ["/new"]},
                {
                    "Field": "http-header",
                    "HttpHeaderConfig": {"HttpHeaderName": "x-ce-origin-verify", "Values": ["live-secret"]},
                },
            ],
        )
        origin_condition.assert_not_called()

    @patch("lib.cli.ce_router_killswitch._origin_verify_condition", return_value=ORIGIN_CONDITION)
    def test_keeps_other_conditions_and_drops_empty_legacy_values(self, _origin_condition):
        other = {"Field": "source-ip", "Values": [], "SourceIpConfig": {"Values": ["10.0.0.0/8"]}}
        rule = {"Conditions": [other]}
        self.assertEqual(
            rule_conditions_with_paths(rule, ["/new"]),
            [
                {"Field": "path-pattern", "Values": ["/new"]},
                {"Field": "source-ip", "SourceIpConfig": {"Values": ["10.0.0.0/8"]}},
                ORIGIN_CONDITION,
            ],
        )


class TestCreatedRule(unittest.TestCase):
    def test_created_rule_requires_origin_header(self):
        alb_client = MagicMock()
        alb_client.describe_rules.return_value = {"Rules": [{"Priority": "default", "Actions": []}]}
        disabled_condition = {"Field": "path-pattern", "Values": ["/killswitch-disabled-staging-*"]}
        alb_client.create_rule.return_value = {
            "Rules": [{"RuleArn": "new-rule", "Priority": "71", "Conditions": [disabled_condition, ORIGIN_CONDITION]}]
        }
        with (
            patch("lib.cli.ce_router_killswitch._get_alb_client", return_value=alb_client),
            patch(
                "lib.cli.ce_router_killswitch._find_ce_router_target_groups",
                return_value={"staging": {"arn": "tg-arn", "name": "ce-router-staging"}},
            ),
            patch("lib.cli.ce_router_killswitch._find_compiler_explorer_listener", return_value="listener-arn"),
            patch("lib.cli.ce_router_killswitch._origin_verify_condition", return_value=ORIGIN_CONDITION),
        ):
            result = CliRunner().invoke(
                enable, ["-e", "staging", "--skip-confirmation"], obj=Config(env=Environment.STAGING)
            )

        self.assertEqual(result.exit_code, 0)
        alb_client.create_rule.assert_called_once_with(
            ListenerArn="listener-arn",
            Priority=71,
            Conditions=[disabled_condition, ORIGIN_CONDITION],
            Actions=[{"Type": "forward", "TargetGroupArn": "tg-arn"}],
        )
        enabled_conditions = alb_client.modify_rule.call_args.kwargs["Conditions"]
        self.assertEqual(enabled_conditions[0]["Values"], compilation_path_patterns("staging"))
        self.assertIn(ORIGIN_CONDITION, enabled_conditions)


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

    def _invoke(self, rule_conditions, command=enable):
        rule = {"RuleArn": "rule-arn", "Priority": "70", "Conditions": rule_conditions}
        with (
            patch("lib.cli.ce_router_killswitch._get_alb_client", return_value=self.alb_client),
            patch(
                "lib.cli.ce_router_killswitch._find_ce_router_target_groups",
                return_value={"prod": {"arn": "tg-arn", "name": "ce-router-prod"}},
            ),
            patch("lib.cli.ce_router_killswitch._find_compiler_explorer_listener", return_value="listener-arn"),
            patch("lib.cli.ce_router_killswitch._find_or_create_ce_router_rules", return_value={"prod": rule}),
            patch("lib.cli.ce_router_killswitch._origin_verify_condition", return_value=ORIGIN_CONDITION),
        ):
            return self.runner.invoke(command, ["-e", "prod", "--skip-confirmation"], obj=self.cfg)

    def test_enable_sets_all_patterns(self):
        result = self._invoke([{"Field": "path-pattern", "Values": ["/killswitch-disabled-prod-*"]}])

        self.assertEqual(result.exit_code, 0)
        self.alb_client.modify_rule.assert_called_once_with(
            RuleArn="rule-arn",
            Conditions=[
                {
                    "Field": "path-pattern",
                    "Values": ["/api/compiler/*/compile", "/api/compiler/*/cmake", "/api/compiler/*/build/*"],
                },
                ORIGIN_CONDITION,
            ],
        )

    def test_enable_keeps_origin_header_condition(self):
        result = self._invoke([{"Field": "path-pattern", "Values": ["/killswitch-disabled-prod-*"]}, ORIGIN_CONDITION])

        self.assertEqual(result.exit_code, 0)
        conditions = self.alb_client.modify_rule.call_args.kwargs["Conditions"]
        self.assertIn(ORIGIN_CONDITION, conditions)

    def test_disable_keeps_origin_header_condition(self):
        result = self._invoke(
            [{"Field": "path-pattern", "Values": compilation_path_patterns("prod")}, ORIGIN_CONDITION],
            command=disable,
        )

        self.assertEqual(result.exit_code, 0)
        self.alb_client.modify_rule.assert_called_once_with(
            RuleArn="rule-arn",
            Conditions=[{"Field": "path-pattern", "Values": ["/killswitch-disabled-prod-*"]}, ORIGIN_CONDITION],
        )

    def test_enable_updates_rule_missing_build_pattern(self):
        result = self._invoke([
            {"Field": "path-pattern", "Values": ["/api/compiler/*/compile", "/api/compiler/*/cmake"]}
        ])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("Updating ce-router ALB path patterns", result.output)
        self.alb_client.modify_rule.assert_called_once()

    def test_enable_leaves_up_to_date_rule_alone(self):
        result = self._invoke([
            {"Field": "path-pattern", "Values": compilation_path_patterns("prod")},
            ORIGIN_CONDITION,
        ])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("already enabled", result.output)
        self.alb_client.modify_rule.assert_not_called()

    def test_enable_adds_origin_header_to_enabled_rule_lacking_it(self):
        result = self._invoke([{"Field": "path-pattern", "Values": compilation_path_patterns("prod")}])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("Adding the CloudFront origin header requirement", result.output)
        self.alb_client.modify_rule.assert_called_once_with(
            RuleArn="rule-arn",
            Conditions=[{"Field": "path-pattern", "Values": compilation_path_patterns("prod")}, ORIGIN_CONDITION],
        )


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
