"""Tests for deployment utility functions."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import requests
from botocore.exceptions import ClientError
from lib.deployment_utils import clear_router_cache


def _response(status_code: int, text: str = "") -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.text = text
    return response


@patch("lib.deployment_utils.time.sleep")
@patch("lib.deployment_utils.is_running_on_admin_node", return_value=True)
class TestClearRouterCache(unittest.TestCase):
    """Test router cache clearing functionality."""

    @patch("lib.deployment_utils.get_instance_private_ip")
    @patch("lib.deployment_utils.get_asg_info")
    @patch("lib.deployment_utils.requests.post")
    def test_clear_router_cache_success(
        self, mock_post, mock_get_asg_info, mock_get_private_ip, _mock_admin_node, _mock_sleep
    ):
        """Test successful router cache clearing."""
        mock_get_asg_info.return_value = {
            "Instances": [
                {"InstanceId": "i-router123", "LifecycleState": "InService"},
            ]
        }
        mock_get_private_ip.return_value = "10.0.1.50"
        mock_post.return_value = _response(200)

        result = clear_router_cache("staging")

        self.assertTrue(result.complete)
        self.assertEqual(result.required, 1)
        self.assertEqual(result.cleared, 1)
        self.assertIsNone(result.not_applicable)
        mock_get_asg_info.assert_called_once_with("ce-router-staging")
        mock_get_private_ip.assert_called_once_with("i-router123")
        mock_post.assert_called_once_with("http://10.0.1.50/admin/clear-cache", timeout=15)

    @patch("lib.deployment_utils.get_asg_info")
    def test_clear_router_cache_not_on_admin_node(self, mock_get_asg_info, mock_admin_node, _mock_sleep):
        """Routers are only reachable from the admin node, so elsewhere there is nothing to do."""
        mock_admin_node.return_value = False

        result = clear_router_cache("prod")

        self.assertIn("ce --env prod ce-router exec_all", result.not_applicable)
        mock_get_asg_info.assert_not_called()

    @patch("lib.deployment_utils.get_asg_info")
    def test_clear_router_cache_asg_not_found(self, mock_get_asg_info, _mock_admin_node, _mock_sleep):
        """Environments without a router ASG are not a failure."""
        mock_get_asg_info.return_value = None

        result = clear_router_cache("gpu")

        self.assertIsNotNone(result.not_applicable)
        self.assertEqual(result.failures, [])
        mock_get_asg_info.assert_called_once_with("ce-router-gpu")

    @patch("lib.deployment_utils.get_asg_info")
    def test_clear_router_cache_no_instances(self, mock_get_asg_info, _mock_admin_node, _mock_sleep):
        """Test behavior when router ASG has no instances."""
        mock_get_asg_info.return_value = {"Instances": []}

        result = clear_router_cache("beta")

        self.assertIsNotNone(result.not_applicable)
        self.assertEqual(result.failures, [])

    @patch("lib.deployment_utils.get_asg_info")
    def test_clear_router_cache_no_in_service_instances(self, mock_get_asg_info, _mock_admin_node, _mock_sleep):
        """Test behavior when no instances are in service."""
        mock_get_asg_info.return_value = {
            "Instances": [
                {"InstanceId": "i-router123", "LifecycleState": "Pending"},
            ]
        }

        result = clear_router_cache("staging")

        self.assertIsNotNone(result.not_applicable)
        self.assertEqual(result.failures, [])

    @patch("lib.deployment_utils.get_instance_private_ip")
    @patch("lib.deployment_utils.get_asg_info")
    def test_clear_router_cache_no_private_ip(
        self, mock_get_asg_info, mock_get_private_ip, _mock_admin_node, _mock_sleep
    ):
        """An instance whose IP cannot be found has not been cleared."""
        mock_get_asg_info.return_value = {
            "Instances": [
                {"InstanceId": "i-router123", "LifecycleState": "InService"},
            ]
        }
        mock_get_private_ip.return_value = None

        result = clear_router_cache("prod")

        self.assertFalse(result.complete)
        self.assertEqual(len(result.failures), 1)

    @patch("lib.deployment_utils.get_instance_private_ip")
    @patch("lib.deployment_utils.get_asg_info")
    @patch("lib.deployment_utils.requests.post")
    def test_clear_router_cache_http_error(
        self, mock_post, mock_get_asg_info, mock_get_private_ip, _mock_admin_node, _mock_sleep
    ):
        """A router that keeps returning an error is retried and then reported."""
        mock_get_asg_info.return_value = {
            "Instances": [
                {"InstanceId": "i-router123", "LifecycleState": "InService"},
            ]
        }
        mock_get_private_ip.return_value = "10.0.1.50"
        mock_post.return_value = _response(500, "Internal error")

        result = clear_router_cache("staging")

        self.assertFalse(result.complete)
        self.assertEqual(mock_post.call_count, 3)
        self.assertIn("HTTP 500", result.failures[0])

    @patch("lib.deployment_utils.get_instance_private_ip")
    @patch("lib.deployment_utils.get_asg_info")
    @patch("lib.deployment_utils.requests.post")
    def test_clear_router_cache_retry_succeeds(
        self, mock_post, mock_get_asg_info, mock_get_private_ip, _mock_admin_node, _mock_sleep
    ):
        """Most partial failures are transient, so a retry counts as success."""
        mock_get_asg_info.return_value = {
            "Instances": [
                {"InstanceId": "i-router123", "LifecycleState": "InService"},
            ]
        }
        mock_get_private_ip.return_value = "10.0.1.50"
        mock_post.side_effect = [requests.exceptions.Timeout("too slow"), _response(200)]

        result = clear_router_cache("prod")

        self.assertTrue(result.complete)
        self.assertEqual(mock_post.call_count, 2)

    @patch("lib.deployment_utils.get_instance_private_ip")
    @patch("lib.deployment_utils.get_asg_info")
    @patch("lib.deployment_utils.requests.post")
    def test_clear_router_cache_connection_error(
        self, mock_post, mock_get_asg_info, mock_get_private_ip, _mock_admin_node, _mock_sleep
    ):
        """Test behavior when connection fails."""
        mock_get_asg_info.return_value = {
            "Instances": [
                {"InstanceId": "i-router123", "LifecycleState": "InService"},
            ]
        }
        mock_get_private_ip.return_value = "10.0.1.50"
        mock_post.side_effect = requests.exceptions.ConnectionError("Connection refused")

        result = clear_router_cache("beta")

        self.assertFalse(result.complete)
        self.assertIn("ConnectionError", result.failures[0])

    @patch("lib.deployment_utils.get_asg_info")
    def test_clear_router_cache_aws_error(self, mock_get_asg_info, _mock_admin_node, _mock_sleep):
        """Test behavior when AWS API call fails."""
        mock_get_asg_info.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "Access denied"}}, "DescribeAutoScalingGroups"
        )

        result = clear_router_cache("staging")

        self.assertFalse(result.complete)
        self.assertEqual(len(result.failures), 1)

    @patch("lib.deployment_utils.get_instance_private_ip")
    @patch("lib.deployment_utils.get_asg_info")
    @patch("lib.deployment_utils.requests.post")
    def test_clear_router_cache_multiple_instances(
        self, mock_post, mock_get_asg_info, mock_get_private_ip, _mock_admin_node, _mock_sleep
    ):
        """Test that cache is cleared on all in-service instances."""
        mock_get_asg_info.return_value = {
            "Instances": [
                {"InstanceId": "i-router1", "LifecycleState": "InService"},
                {"InstanceId": "i-router2", "LifecycleState": "InService"},
            ]
        }
        mock_get_private_ip.side_effect = ["10.0.1.50", "10.0.1.51"]
        mock_post.return_value = _response(200)

        result = clear_router_cache("prod")

        self.assertTrue(result.complete)
        self.assertEqual(result.cleared, 2)
        mock_post.assert_any_call("http://10.0.1.50/admin/clear-cache", timeout=15)
        mock_post.assert_any_call("http://10.0.1.51/admin/clear-cache", timeout=15)

    @patch("lib.deployment_utils.get_instance_private_ip")
    @patch("lib.deployment_utils.get_asg_info")
    @patch("lib.deployment_utils.requests.post")
    def test_clear_router_cache_partial_is_not_success(
        self, mock_post, mock_get_asg_info, mock_get_private_ip, _mock_admin_node, _mock_sleep
    ):
        """Reaching one of several routers leaves the others serving the old colour."""
        mock_get_asg_info.return_value = {
            "Instances": [
                {"InstanceId": "i-router1", "LifecycleState": "InService"},
                {"InstanceId": "i-router2", "LifecycleState": "InService"},
            ]
        }
        mock_get_private_ip.side_effect = ["10.0.1.50", "10.0.1.51"]
        mock_post.side_effect = [_response(200), _response(500, "Internal error"), _response(500), _response(500)]

        result = clear_router_cache("staging")

        self.assertFalse(result.complete)
        self.assertEqual(result.cleared, 1)
        self.assertEqual(result.required, 2)
        self.assertEqual(len(result.failures), 1)
        self.assertIn("i-router2", result.failures[0])

    @patch("lib.deployment_utils.get_instance_private_ip")
    @patch("lib.deployment_utils.get_asg_info")
    @patch("lib.deployment_utils.requests.post")
    def test_clear_router_cache_other_states_are_best_effort(
        self, mock_post, mock_get_asg_info, mock_get_private_ip, _mock_admin_node, _mock_sleep
    ):
        """A router that is not in service is tried once and cannot fail the clear."""
        mock_get_asg_info.return_value = {
            "Instances": [
                {"InstanceId": "i-router1", "LifecycleState": "InService"},
                {"InstanceId": "i-router2", "LifecycleState": "Pending"},
                {"InstanceId": "i-router3", "LifecycleState": "Terminating:Wait"},
            ]
        }
        mock_get_private_ip.side_effect = ["10.0.1.50", "10.0.1.51"]
        mock_post.side_effect = [_response(200), requests.exceptions.ConnectionError("not listening yet")]

        result = clear_router_cache("prod")

        self.assertTrue(result.complete)
        self.assertEqual(result.required, 1)
        self.assertEqual(mock_post.call_count, 2)
        mock_post.assert_any_call("http://10.0.1.51/admin/clear-cache", timeout=15)


if __name__ == "__main__":
    unittest.main()
