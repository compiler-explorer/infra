"""Tests for CloudFront invalidation during blue-green deployments."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import lib.cli  # noqa: F401 (must import before blue_green_deploy to avoid circular import)
from lib.blue_green_deploy import BlueGreenDeployment
from lib.env import Config, Environment


class TestDeployCloudFrontInvalidation(unittest.TestCase):
    """The deploy flow invalidates CloudFront after the compiler routing update."""

    def _run_deploy(self, skip_cloudfront: bool) -> tuple[MagicMock, MagicMock, list[str]]:
        with patch("lib.blue_green_deploy.ssm_client"), patch("lib.blue_green_deploy.is_running_on_admin_node"):
            deployment = BlueGreenDeployment(Config(env=Environment.PROD))
        deployment.running_on_admin_node = False

        with (
            patch.object(deployment, "get_active_color", return_value="blue"),
            patch.object(deployment, "get_inactive_color", return_value="green"),
            patch.object(deployment, "get_asg_name", side_effect=lambda color: f"prod-{color}"),
            patch.object(deployment, "switch_target_group") as mock_switch,
            patch("lib.blue_green_deploy.get_asg_info", return_value={"DesiredCapacity": 0}),
            patch("lib.blue_green_deploy.protect_asg_capacity", return_value=(1, 4)),
            patch("lib.blue_green_deploy.scale_asg"),
            patch("lib.blue_green_deploy.wait_for_instances_healthy", return_value=["i-1"]),
            patch("lib.blue_green_deploy.clear_router_cache", return_value=True),
            patch("lib.blue_green_deploy.reset_asg_min_size"),
            patch("lib.blue_green_deploy.restore_asg_capacity_protection"),
            patch("lib.blue_green_deploy.get_instance_private_ip", return_value="10.0.0.1"),
            patch("lib.blue_green_deploy.update_compiler_routing_table") as mock_routing,
            patch("lib.blue_green_deploy.invalidate_cloudfront_distributions") as mock_invalidate,
            patch("builtins.print"),
        ):
            manager = MagicMock()
            manager.attach_mock(mock_switch, "switch")
            manager.attach_mock(mock_routing, "routing")
            manager.attach_mock(mock_invalidate, "cloudfront")
            mock_routing.return_value = {"added": 0, "updated": 0, "deleted": 0}

            deployment.deploy(
                target_capacity=1,
                skip_confirmation=True,
                skip_compiler_check=True,
                skip_cloudfront=skip_cloudfront,
            )

            order = [name for name, _args, _kwargs in manager.mock_calls]

        return mock_switch, mock_invalidate, order

    def test_invalidates_after_routing_update(self):
        mock_switch, mock_invalidate, order = self._run_deploy(skip_cloudfront=False)
        mock_switch.assert_called_once_with("green")
        mock_invalidate.assert_called_once()
        assert mock_invalidate.call_args[0][0].env == Environment.PROD
        assert order == ["switch", "routing", "cloudfront"]

    def test_skip_cloudfront_suppresses_invalidation(self):
        mock_switch, mock_invalidate, order = self._run_deploy(skip_cloudfront=True)
        mock_switch.assert_called_once_with("green")
        mock_invalidate.assert_not_called()
        assert order == ["switch", "routing"]


if __name__ == "__main__":
    unittest.main()
