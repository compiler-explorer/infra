"""Tests for deployment utility functions."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import requests
from botocore.exceptions import ClientError
from lib.deployment_utils import clear_router_cache


class TestClearRouterCache(unittest.TestCase):
    """Test router cache clearing functionality."""

    @patch("lib.deployment_utils.get_instance_private_ip")
    @patch("lib.deployment_utils.get_asg_info")
    @patch("lib.deployment_utils.requests.post")
    def test_clear_router_cache_success(self, mock_post, mock_get_asg_info, mock_get_private_ip):
        """Test successful router cache clearing."""
        mock_get_asg_info.return_value = {
            "Instances": [
                {"InstanceId": "i-router123", "LifecycleState": "InService"},
            ]
        }
        mock_get_private_ip.return_value = "10.0.1.50"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        result = clear_router_cache("staging")

        self.assertTrue(result)
        mock_get_asg_info.assert_called_once_with("ce-router-staging")
        mock_get_private_ip.assert_called_once_with("i-router123")
        mock_post.assert_called_once_with("http://10.0.1.50:10240/admin/clear-cache", timeout=5)

    @patch("lib.deployment_utils.get_asg_info")
    def test_clear_router_cache_asg_not_found(self, mock_get_asg_info):
        """Test behavior when router ASG is not found."""
        mock_get_asg_info.return_value = None

        result = clear_router_cache("prod")

        self.assertFalse(result)
        mock_get_asg_info.assert_called_once_with("ce-router-prod")

    @patch("lib.deployment_utils.get_asg_info")
    def test_clear_router_cache_no_instances(self, mock_get_asg_info):
        """Test behavior when router ASG has no instances."""
        mock_get_asg_info.return_value = {"Instances": []}

        result = clear_router_cache("beta")

        self.assertFalse(result)
        mock_get_asg_info.assert_called_once_with("ce-router-beta")

    @patch("lib.deployment_utils.get_asg_info")
    def test_clear_router_cache_no_in_service_instances(self, mock_get_asg_info):
        """Test behavior when router ASG has no in-service instances."""
        mock_get_asg_info.return_value = {
            "Instances": [
                {"InstanceId": "i-router123", "LifecycleState": "Pending"},
            ]
        }

        result = clear_router_cache("staging")

        self.assertFalse(result)

    @patch("lib.deployment_utils.get_instance_private_ip")
    @patch("lib.deployment_utils.get_asg_info")
    def test_clear_router_cache_no_private_ip(self, mock_get_asg_info, mock_get_private_ip):
        """Test behavior when router instance has no private IP."""
        mock_get_asg_info.return_value = {
            "Instances": [
                {"InstanceId": "i-router123", "LifecycleState": "InService"},
            ]
        }
        mock_get_private_ip.return_value = None

        result = clear_router_cache("prod")

        self.assertFalse(result)

    @patch("lib.deployment_utils.get_instance_private_ip")
    @patch("lib.deployment_utils.get_asg_info")
    @patch("lib.deployment_utils.requests.post")
    def test_clear_router_cache_http_error(self, mock_post, mock_get_asg_info, mock_get_private_ip):
        """Test behavior when cache clear endpoint returns non-200 status."""
        mock_get_asg_info.return_value = {
            "Instances": [
                {"InstanceId": "i-router123", "LifecycleState": "InService"},
            ]
        }
        mock_get_private_ip.return_value = "10.0.1.50"

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_post.return_value = mock_response

        result = clear_router_cache("staging")

        self.assertFalse(result)

    @patch("lib.deployment_utils.get_instance_private_ip")
    @patch("lib.deployment_utils.get_asg_info")
    @patch("lib.deployment_utils.requests.post")
    def test_clear_router_cache_timeout(self, mock_post, mock_get_asg_info, mock_get_private_ip):
        """Test behavior when cache clear request times out."""
        mock_get_asg_info.return_value = {
            "Instances": [
                {"InstanceId": "i-router123", "LifecycleState": "InService"},
            ]
        }
        mock_get_private_ip.return_value = "10.0.1.50"
        mock_post.side_effect = requests.exceptions.Timeout("Timeout")

        result = clear_router_cache("prod")

        self.assertFalse(result)

    @patch("lib.deployment_utils.get_instance_private_ip")
    @patch("lib.deployment_utils.get_asg_info")
    @patch("lib.deployment_utils.requests.post")
    def test_clear_router_cache_connection_error(self, mock_post, mock_get_asg_info, mock_get_private_ip):
        """Test behavior when cache clear request has connection error."""
        mock_get_asg_info.return_value = {
            "Instances": [
                {"InstanceId": "i-router123", "LifecycleState": "InService"},
            ]
        }
        mock_get_private_ip.return_value = "10.0.1.50"
        mock_post.side_effect = requests.exceptions.ConnectionError("Connection refused")

        result = clear_router_cache("beta")

        self.assertFalse(result)

    @patch("lib.deployment_utils.get_asg_info")
    def test_clear_router_cache_aws_error(self, mock_get_asg_info):
        """Test behavior when AWS API returns an error."""
        mock_get_asg_info.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "Access denied"}}, "DescribeAutoScalingGroups"
        )

        result = clear_router_cache("staging")

        self.assertFalse(result)

    @patch("lib.deployment_utils.get_instance_private_ip")
    @patch("lib.deployment_utils.get_asg_info")
    @patch("lib.deployment_utils.requests.post")
    def test_clear_router_cache_multiple_instances(self, mock_post, mock_get_asg_info, mock_get_private_ip):
        """Test that cache is cleared on all in-service instances."""
        mock_get_asg_info.return_value = {
            "Instances": [
                {"InstanceId": "i-router1", "LifecycleState": "InService"},
                {"InstanceId": "i-router2", "LifecycleState": "InService"},
            ]
        }
        mock_get_private_ip.side_effect = ["10.0.1.50", "10.0.1.51"]

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        result = clear_router_cache("prod")

        self.assertTrue(result)
        self.assertEqual(mock_get_private_ip.call_count, 2)
        self.assertEqual(mock_post.call_count, 2)
        mock_post.assert_any_call("http://10.0.1.50:10240/admin/clear-cache", timeout=5)
        mock_post.assert_any_call("http://10.0.1.51:10240/admin/clear-cache", timeout=5)

    @patch("lib.deployment_utils.get_instance_private_ip")
    @patch("lib.deployment_utils.get_asg_info")
    @patch("lib.deployment_utils.requests.post")
    def test_clear_router_cache_partial_success(self, mock_post, mock_get_asg_info, mock_get_private_ip):
        """Test that function returns True if at least one instance succeeds."""
        mock_get_asg_info.return_value = {
            "Instances": [
                {"InstanceId": "i-router1", "LifecycleState": "InService"},
                {"InstanceId": "i-router2", "LifecycleState": "InService"},
            ]
        }
        mock_get_private_ip.side_effect = ["10.0.1.50", "10.0.1.51"]

        mock_success = MagicMock()
        mock_success.status_code = 200
        mock_failure = MagicMock()
        mock_failure.status_code = 500
        mock_failure.text = "Internal error"
        mock_post.side_effect = [mock_success, mock_failure]

        result = clear_router_cache("staging")

        self.assertTrue(result)
        self.assertEqual(mock_post.call_count, 2)

    @patch("lib.deployment_utils.get_instance_private_ip")
    @patch("lib.deployment_utils.get_asg_info")
    @patch("lib.deployment_utils.requests.post")
    def test_clear_router_cache_skip_instance_without_ip(self, mock_post, mock_get_asg_info, mock_get_private_ip):
        """Test that instances without private IPs are skipped."""
        mock_get_asg_info.return_value = {
            "Instances": [
                {"InstanceId": "i-router1", "LifecycleState": "InService"},
                {"InstanceId": "i-router2", "LifecycleState": "InService"},
            ]
        }
        mock_get_private_ip.side_effect = [None, "10.0.1.51"]

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        result = clear_router_cache("beta")

        self.assertTrue(result)
        self.assertEqual(mock_get_private_ip.call_count, 2)
        self.assertEqual(mock_post.call_count, 1)
        mock_post.assert_called_once_with("http://10.0.1.51:10240/admin/clear-cache", timeout=5)


if __name__ == "__main__":
    unittest.main()
