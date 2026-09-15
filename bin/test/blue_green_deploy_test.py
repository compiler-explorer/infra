from __future__ import annotations

import unittest
from unittest.mock import patch

import lib.cli  # noqa: F401 (must import before blue_green_deploy to avoid circular import)
from lib.blue_green_deploy import BlueGreenDeployment, rule_forwards_for_path
from lib.env import Config, Environment

PROD_RULE = {
    "RuleArn": "prod-rule",
    "Priority": "1000",
    "Conditions": [
        {"Field": "path-pattern", "Values": ["/*"]},
        {"Field": "http-header", "HttpHeaderConfig": {"HttpHeaderName": "X-CE-Origin-Verify", "Values": ["s"]}},
    ],
    "Actions": [{"Type": "forward", "TargetGroupArn": "prod-blue"}],
}
STAGING_RULE = {
    "RuleArn": "staging-rule",
    "Priority": "111",
    "Conditions": [{"Field": "path-pattern", "Values": ["/staging*"]}],
    "Actions": [{"Type": "forward", "TargetGroupArn": "staging-blue"}],
}
DENY_RULE = {
    "RuleArn": "deny-rule",
    "Priority": "50000",
    "Conditions": [{"Field": "path-pattern", "Values": ["/*"]}],
    "Actions": [{"Type": "fixed-response", "FixedResponseConfig": {"StatusCode": "403"}}],
}
DEFAULT_RULE = {"RuleArn": "default-rule", "Priority": "default", "Conditions": [], "Actions": []}


class TestRuleForwardsForPath(unittest.TestCase):
    def test_matches_forwarding_rule_with_pattern(self):
        self.assertTrue(rule_forwards_for_path(PROD_RULE, "/*"))
        self.assertTrue(rule_forwards_for_path(STAGING_RULE, "/staging*"))

    def test_ignores_deny_rule_sharing_prod_pattern(self):
        self.assertFalse(rule_forwards_for_path(DENY_RULE, "/*"))

    def test_ignores_rules_for_other_patterns(self):
        self.assertFalse(rule_forwards_for_path(STAGING_RULE, "/*"))
        self.assertFalse(rule_forwards_for_path(PROD_RULE, "/staging*"))


@patch("lib.blue_green_deploy.is_running_on_admin_node", return_value=False)
@patch("lib.blue_green_deploy.elb_client")
class TestSwitchTargetGroup(unittest.TestCase):
    def _setup_alb(self, elb_client, rules):
        elb_client.describe_load_balancers.return_value = {"LoadBalancers": [{"LoadBalancerArn": "alb-arn"}]}
        elb_client.describe_listeners.return_value = {
            "Listeners": [{"Port": 80, "ListenerArn": "http-listener"}, {"Port": 443, "ListenerArn": "https-listener"}]
        }
        elb_client.describe_rules.return_value = {"Rules": rules}

    def _switch(self, env: Environment, color: str) -> None:
        deployment = BlueGreenDeployment(Config(env=env))
        with (
            patch.object(deployment, "get_target_group_arn", return_value=f"{env.value}-{color}"),
            patch.object(deployment, "_update_ssm_parameters"),
        ):
            deployment.switch_target_group(color)

    def test_prod_switches_catch_all_rule_not_listener_default(self, elb_client, _admin_node):
        self._setup_alb(elb_client, [DENY_RULE, STAGING_RULE, PROD_RULE, DEFAULT_RULE])

        self._switch(Environment.PROD, "green")

        elb_client.modify_rule.assert_called_once_with(
            RuleArn="prod-rule", Actions=[{"Type": "forward", "TargetGroupArn": "prod-green"}]
        )
        elb_client.modify_listener.assert_not_called()

    def test_staging_switches_its_path_rule(self, elb_client, _admin_node):
        self._setup_alb(elb_client, [DENY_RULE, STAGING_RULE, PROD_RULE, DEFAULT_RULE])

        self._switch(Environment.STAGING, "green")

        elb_client.modify_rule.assert_called_once_with(
            RuleArn="staging-rule", Actions=[{"Type": "forward", "TargetGroupArn": "staging-green"}]
        )

    def test_prod_refuses_to_deploy_without_catch_all_rule(self, elb_client, _admin_node):
        self._setup_alb(elb_client, [DENY_RULE, STAGING_RULE, DEFAULT_RULE])

        with self.assertRaises(ValueError):
            self._switch(Environment.PROD, "green")

        elb_client.modify_rule.assert_not_called()
        elb_client.modify_listener.assert_not_called()
