"""Tests for the blue-green deployment sequence."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import lib.cli  # noqa: F401 (must import before blue_green_deploy to avoid circular import)
from botocore.exceptions import ClientError
from lib.blue_green_deploy import BlueGreenDeployment
from lib.deployment_utils import RouterCacheClearResult
from lib.env import Config, Environment


class TestRouterCacheOrdering(unittest.TestCase):
    """The router cache clear has to come after everything it invalidates.

    A router caches the resolved queue URL (active colour substituted) and the routing row
    with no TTL, so clearing before the active colour is written to SSM, or before the
    routing table is updated, refills the cache with the values the clear was meant to drop.
    """

    def setUp(self):
        with patch("lib.blue_green_deploy.is_running_on_admin_node", return_value=False):
            self.deployment = BlueGreenDeployment(Config(env=Environment.STAGING))
        self.manager = MagicMock()

    def _patch(self, name: str, **kwargs) -> MagicMock:
        patcher = patch(f"lib.blue_green_deploy.{name}", **kwargs)
        mock = patcher.start()
        self.addCleanup(patcher.stop)
        self.manager.attach_mock(mock, name)
        return mock

    def _patch_method(self, name: str, **kwargs) -> MagicMock:
        patcher = patch.object(BlueGreenDeployment, name, **kwargs)
        mock = patcher.start()
        self.addCleanup(patcher.stop)
        self.manager.attach_mock(mock, name)
        return mock

    def _called_names(self) -> list[str]:
        return [call[0] for call in self.manager.mock_calls]

    def test_deploy_clears_router_cache_after_switch_and_routing_update(self):
        self._patch_method("get_active_color", return_value="blue")
        self._patch_method("get_inactive_color", return_value="green")
        self._patch_method("get_asg_name", side_effect=lambda color: f"staging-{color}")
        self._patch_method("switch_target_group")
        self._patch("get_asg_info", return_value={"DesiredCapacity": 0, "Instances": []})
        self._patch("protect_asg_capacity", return_value=(0, 4))
        self._patch("scale_asg")
        self._patch("wait_for_instances_healthy", return_value=["i-new1"])
        self._patch("reset_asg_min_size")
        self._patch("restore_asg_capacity_protection")
        self._patch("get_instance_private_ip", return_value="10.0.0.1")
        self._patch("update_compiler_routing_table", return_value={"added": 1, "updated": 0, "deleted": 0})
        self._patch("clear_router_cache", return_value=RouterCacheClearResult(required=1, cleared=1))

        self.deployment.deploy(target_capacity=1, skip_confirmation=True, skip_compiler_check=True)

        called = self._called_names()
        self.assertIn("clear_router_cache", called)
        self.assertLess(called.index("switch_target_group"), called.index("clear_router_cache"))
        self.assertLess(called.index("update_compiler_routing_table"), called.index("clear_router_cache"))

    def test_deploy_clears_router_cache_even_if_routing_update_fails(self):
        """Step 6 swallows its own errors, so the clear must not be nested inside it."""
        self._patch_method("get_active_color", return_value="blue")
        self._patch_method("get_inactive_color", return_value="green")
        self._patch_method("get_asg_name", side_effect=lambda color: f"staging-{color}")
        self._patch_method("switch_target_group")
        self._patch("get_asg_info", return_value={"DesiredCapacity": 0, "Instances": []})
        self._patch("protect_asg_capacity", return_value=(0, 4))
        self._patch("scale_asg")
        self._patch("wait_for_instances_healthy", return_value=["i-new1"])
        self._patch("reset_asg_min_size")
        self._patch("restore_asg_capacity_protection")
        self._patch("get_instance_private_ip", return_value="10.0.0.1")
        routing = self._patch("update_compiler_routing_table")
        routing.side_effect = ClientError({"Error": {"Code": "AccessDenied", "Message": "nope"}}, "PutItem")
        clear = self._patch("clear_router_cache", return_value=RouterCacheClearResult(required=1, cleared=1))

        self.deployment.deploy(target_capacity=1, skip_confirmation=True, skip_compiler_check=True)

        clear.assert_called_once_with("staging")

    def test_rollback_clears_router_cache(self):
        """Rollback is the worst case: the routers still point at the bad colour."""
        self._patch_method("get_active_color", return_value="green")
        self._patch_method("get_inactive_color", return_value="blue")
        self._patch_method("get_asg_name", side_effect=lambda color: f"staging-{color}")
        self._patch_method("switch_target_group")
        self._patch("get_asg_info", return_value={"DesiredCapacity": 2, "Instances": []})
        clear = self._patch("clear_router_cache", return_value=RouterCacheClearResult(required=1, cleared=1))

        self.deployment.rollback()

        clear.assert_called_once_with("staging")
        called = self._called_names()
        self.assertLess(called.index("switch_target_group"), called.index("clear_router_cache"))


class TestRouterCacheReporting(unittest.TestCase):
    """A partial clear has to be loud: nothing else will ever fix those routers."""

    def setUp(self):
        with patch("lib.blue_green_deploy.is_running_on_admin_node", return_value=False):
            self.deployment = BlueGreenDeployment(Config(env=Environment.PROD))

    def _clear_with(self, result: RouterCacheClearResult) -> list[str]:
        with (
            patch("lib.blue_green_deploy.clear_router_cache", return_value=result),
            patch("builtins.print") as mock_print,
        ):
            self.deployment.clear_router_caches()
        return [str(call[0][0]) for call in mock_print.call_args_list if call[0]]

    def test_complete_clear_is_quiet(self):
        output = self._clear_with(RouterCacheClearResult(required=2, cleared=2))

        self.assertTrue(any("✓" in line for line in output))
        self.assertFalse(any("❌" in line for line in output))

    def test_partial_clear_reports_remediation(self):
        result = RouterCacheClearResult(required=2, cleared=1, failures=["i-router2 (10.0.0.2): HTTP 500"])

        output = self._clear_with(result)

        self.assertTrue(any("❌" in line for line in output))
        self.assertTrue(any("/admin/clear-cache" in line for line in output))

    def test_partial_clear_does_not_raise(self):
        """Traffic is already switched by this point; failing here would strip the live ASG."""
        result = RouterCacheClearResult(required=2, cleared=0, failures=["i-router1: no private IP"])

        self._clear_with(result)

    def test_environment_without_routers_is_not_a_failure(self):
        output = self._clear_with(RouterCacheClearResult(not_applicable="No router ASG ce-router-gpu"))

        self.assertFalse(any("❌" in line for line in output))


if __name__ == "__main__":
    unittest.main()
