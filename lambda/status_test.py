import os
import unittest
from unittest.mock import MagicMock, patch
import json
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
            "branch": "release",
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

    @patch("status.s3_client")
    @patch("status.lb_client")
    def test_get_environment_status(self, mock_lb, mock_s3):
        # Mock S3 response
        mock_s3.get_object.return_value = {"Body": MagicMock(read=lambda: b"abc123")}

        # Mock load balancer response
        mock_lb.describe_target_health.return_value = {
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
            "branch": "release",
            "url": "godbolt.org",
            "load_balancer": "arn:aws:elasticloadbalancing:us-east-1:123456789012:targetgroup/prod/abcdef",
        }

        # Call the function
        result = status.get_environment_status(env)

        # Verify results
        self.assertEqual(result["name"], "prod")
        self.assertEqual(result["version"], "abc123")
        self.assertEqual(result["health"]["healthy_targets"], 2)
        self.assertEqual(result["health"]["total_targets"], 3)
        self.assertEqual(result["health"]["status"], "Online")

        # Verify S3 client was called
        mock_s3.get_object.assert_called_once_with(Bucket="compiler-explorer", Key="version/release")

        # Verify load balancer client was called
        mock_lb.describe_target_health.assert_called_once_with(TargetGroupArn=env["load_balancer"])

    @patch("status.s3_client")
    def test_get_environment_status_no_lb(self, mock_s3):
        # Mock S3 response
        mock_s3.get_object.return_value = {"Body": MagicMock(read=lambda: b"def456")}

        # Test environment without load balancer
        env = {"name": "test", "description": "Test", "branch": "release", "url": "test.godbolt.org"}

        # Call the function
        result = status.get_environment_status(env)

        # Verify results
        self.assertEqual(result["version"], "def456")
        self.assertEqual(result["health"]["status"], "Unknown")
        self.assertIn("error", result["health"])


if __name__ == "__main__":
    unittest.main()
