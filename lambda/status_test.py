import json
import os
import unittest
from unittest.mock import MagicMock, patch

import status


class TestStatusLambda(unittest.TestCase):
    def setUp(self):
        # Mock environment variables
        os.environ["PROD_LB_ARN"] = "arn:aws:elasticloadbalancing:us-east-1:123456789012:targetgroup/prod/abcdef"

        # Create a minimal event
        self.event = {
            "httpMethod": "GET",
        }

    @patch("status.get_environment_status")
    def test_lambda_handler_success(self, mock_get_status):
        # Set up the mock
        mock_get_status.return_value = {
            "name": "prod",
            "description": "Production",
            "url": "godbolt.org",
            "is_production": True,
            "version": "abc123",
            "health": {"healthy_targets": 2, "total_targets": 3, "status": "Online"},
        }

        # Call the lambda_handler
        response = status.lambda_handler(self.event, None)

        # Verify response
        self.assertEqual(response["statusCode"], 200)
        self.assertIn("application/json", response["headers"]["Content-Type"])

        # Parse the body
        body = json.loads(response["body"])
        self.assertIn("environments", body)
        self.assertIn("timestamp", body)

        # Verify the mock was called for each environment
        self.assertEqual(mock_get_status.call_count, len(status.ENVIRONMENTS))

    @patch("status.get_environment_status")
    def test_lambda_handler_options(self, mock_get_status):
        # Set up an OPTIONS event
        options_event = {
            "httpMethod": "OPTIONS",
        }

        # Call the lambda_handler
        response = status.lambda_handler(options_event, None)

        # Verify CORS headers
        self.assertEqual(response["statusCode"], 200)
        self.assertIn("Access-Control-Allow-Origin", response["headers"])

        # Verify the mock was not called
        mock_get_status.assert_not_called()

    @patch("status.get_s3_client")
    @patch("status.get_lb_client")
    @patch("status.get_as_client")
    def test_get_environment_status(self, mock_as_client, mock_lb_client, mock_s3_client):
        # Mock S3 response
        mock_s3_client.return_value.get_object.return_value = {"Body": MagicMock(read=lambda: b"abc123")}

        # Mock AutoScaling response
        mock_as_client.return_value.describe_auto_scaling_groups.return_value = {
            "AutoScalingGroups": [{"AutoScalingGroupName": "prod", "DesiredCapacity": 2, "MinSize": 2, "MaxSize": 24}]
        }

        # Mock load balancer response
        mock_lb_client.return_value.describe_target_health.return_value = {
            "TargetHealthDescriptions": [
                {"TargetHealth": {"State": "healthy"}},
                {"TargetHealth": {"State": "healthy"}},
                {"TargetHealth": {"State": "unhealthy"}},
            ]
        }

        # Test environment
        env = {
            "name": "prod",
            "description": "Production",
            "url": "godbolt.org",
            "load_balancer": "arn:aws:elasticloadbalancing:us-east-1:123456789012:targetgroup/prod/abcdef",
            "is_production": True,
            "version_key": "version/release",
        }

        # Call the function
        result = status.get_environment_status(env)

        # Verify results
        self.assertEqual(result["name"], "prod")
        self.assertEqual(result["version"], "abc123")
        self.assertEqual(result["health"]["healthy_targets"], 2)
        self.assertEqual(result["health"]["total_targets"], 3)
        self.assertEqual(result["health"]["status"], "Online")
        self.assertEqual(result["health"]["status_type"], "success")
        self.assertEqual(result["health"]["desired_capacity"], 2)

        # Verify S3 client was called
        mock_s3_client.return_value.get_object.assert_called_once_with(
            Bucket="compiler-explorer", Key=env["version_key"]
        )

        # Verify load balancer client was called
        mock_lb_client.return_value.describe_target_health.assert_called_once_with(TargetGroupArn=env["load_balancer"])

    @patch("status.get_s3_client")
    @patch("status.get_as_client")
    def test_get_environment_status_deliberate_shutdown(self, mock_as_client, mock_s3_client):
        """Test that we correctly identify environments that are deliberately shut down"""
        # Mock S3 response
        mock_s3_client.return_value.get_object.return_value = {"Body": MagicMock(read=lambda: b"abc123")}

        # Mock AutoScaling response - desired capacity is 0
        mock_as_client.return_value.describe_auto_scaling_groups.return_value = {
            "AutoScalingGroups": [{"AutoScalingGroupName": "beta", "DesiredCapacity": 0, "MinSize": 0, "MaxSize": 4}]
        }

        # Mock LB client inside the status module
        with patch("status.get_lb_client") as mock_lb_client:
            # No healthy targets
            mock_lb_client.return_value.describe_target_health.return_value = {"TargetHealthDescriptions": []}

            # Test environment
            env = {
                "name": "beta",
                "description": "Beta Environment",
                "url": "godbolt.org/beta",
                "load_balancer": "arn:aws:elasticloadbalancing:us-east-1:123:targetgroup/beta/xyz",
                "is_production": False,
                "version_key": "version/beta",
            }

            # Call the function
            result = status.get_environment_status(env)

            # Verify results - should be "Shut down" not "Offline"
            self.assertEqual(result["health"]["status"], "Shut down")
            self.assertEqual(result["health"]["status_type"], "secondary")
            self.assertEqual(result["health"]["desired_capacity"], 0)

    @patch("status.get_s3_client")
    def test_get_environment_status_no_lb(self, mock_s3_client):
        # Mock S3 response
        mock_s3_client.return_value.get_object.return_value = {"Body": MagicMock(read=lambda: b"def456")}

        # Test environment without load balancer
        env = {
            "name": "test",
            "description": "Test",
            "url": "test.godbolt.org",
            "is_production": False,
            "version_key": "version/release",
        }

        # Call the function
        result = status.get_environment_status(env)

        # Verify results
        self.assertEqual(result["version"], "def456")
        self.assertEqual(result["health"]["status"], "Unknown")
        self.assertIn("error", result["health"])

    def test_extract_version_from_key(self):
        """Test the essential version key extraction functionality"""
        # Main case we care about: GitHub versions
        self.assertEqual(status.extract_version_from_key("dist/gh/main/12345.tar.xz"), "gh-12345")

        # Branch names with slashes
        self.assertEqual(status.extract_version_from_key("dist/gh/mg/wasming/14615.tar.xz"), "gh-14615")
        self.assertEqual(status.extract_version_from_key("dist/gh/feature/new-ui/99999.tar.xz"), "gh-99999")

        # Already formatted correctly
        self.assertEqual(status.extract_version_from_key("gh-12345"), "gh-12345")

        # Simple fallback case
        self.assertEqual(status.extract_version_from_key("some-version"), "some-version")

    @patch("status.get_s3_client")
    def test_fetch_commit_hash(self, mock_s3_client):
        """Test hash fetching functionality"""
        # Clear the cache for this test
        status.fetch_commit_hash.cache_clear()

        # Valid hash
        mock_s3_client.return_value.get_object.return_value = {
            "Body": MagicMock(read=lambda: b"1234567890abcdef1234567890abcdef12345678")
        }
        result = status.fetch_commit_hash("dist/gh/main/12345.txt")
        self.assertEqual(result["hash"], "1234567890abcdef1234567890abcdef12345678")
        self.assertEqual(result["hash_short"], "1234567")

        # Handle exceptions - use a different key to avoid cache
        mock_s3_client.return_value.get_object.side_effect = Exception("Test error")
        result = status.fetch_commit_hash("dist/gh/main/98765.txt")  # Different key to avoid cache
        self.assertIsNone(result)

    def test_parse_version_info(self):
        """Test version parsing for the main cases we care about"""
        # GitHub version with path
        with patch("status.fetch_commit_hash") as mock_fetch:
            mock_fetch.return_value = {
                "hash": "1234567890abcdef1234567890abcdef12345678",
                "hash_short": "1234567",
                "hash_url": "https://github.com/compiler-explorer/compiler-explorer/tree/1234567890abcdef1234567890abcdef12345678",
            }

            result = status.parse_version_info("dist/gh/main/12345.tar.xz")
            self.assertEqual(result["version"], "gh-12345")
            self.assertEqual(result["type"], "GitHub")
            self.assertEqual(result["version_num"], "12345")
            self.assertEqual(result["branch"], "main")
            self.assertEqual(result["hash"], "1234567890abcdef1234567890abcdef12345678")

        # Branch with slashes
        with patch("status.fetch_commit_hash") as mock_fetch:
            mock_fetch.return_value = {
                "hash": "1234567890abcdef1234567890abcdef12345678",
                "hash_short": "1234567",
                "hash_url": "https://github.com/compiler-explorer/compiler-explorer/tree/1234567890abcdef1234567890abcdef12345678",
            }

            result = status.parse_version_info("dist/gh/mg/wasming/14615.tar.xz")
            self.assertEqual(result["version"], "gh-14615")
            self.assertEqual(result["type"], "GitHub")
            self.assertEqual(result["version_num"], "14615")
            self.assertEqual(result["branch"], "mg/wasming")
            self.assertEqual(result["hash"], "1234567890abcdef1234567890abcdef12345678")

        # Basic fallback
        with patch("status.fetch_commit_hash") as mock_fetch:
            mock_fetch.return_value = None

            result = status.parse_version_info("some-version")
            self.assertEqual(result["version"], "some-version")
            self.assertEqual(result["hash"], "unknown")


if __name__ == "__main__":
    unittest.main()
