import unittest
from unittest.mock import patch

from botocore.exceptions import ClientError
from lib.cloudfront_config import CLOUDFRONT_INVALIDATION_CONFIG
from lib.cloudfront_utils import (
    create_cloudfront_invalidation,
    invalidate_cloudfront_distributions,
    wait_for_invalidation,
)
from lib.env import Config, Environment


class TestCloudFrontUtils(unittest.TestCase):
    """Tests for CloudFront utility functions."""

    @patch("lib.cloudfront_utils.cloudfront_client")
    def test_create_cloudfront_invalidation(self, mock_client):
        """Test creating a CloudFront invalidation."""
        mock_client.create_invalidation.return_value = {"Invalidation": {"Id": "test-invalidation-id"}}

        result = create_cloudfront_invalidation("test-dist-id", ["/*"])

        assert result == "test-invalidation-id"
        mock_client.create_invalidation.assert_called_once()
        call_args = mock_client.create_invalidation.call_args[1]
        assert call_args["DistributionId"] == "test-dist-id"
        assert call_args["InvalidationBatch"]["Paths"]["Items"] == ["/*"]
        assert call_args["InvalidationBatch"]["Paths"]["Quantity"] == 1
        assert "CallerReference" in call_args["InvalidationBatch"]

    @patch("lib.cloudfront_utils.cloudfront_client")
    def test_create_cloudfront_invalidation_with_caller_reference(self, mock_client):
        """Test creating a CloudFront invalidation with custom caller reference."""
        mock_client.create_invalidation.return_value = {"Invalidation": {"Id": "test-invalidation-id"}}

        result = create_cloudfront_invalidation("test-dist-id", ["/*"], caller_reference="custom-ref")

        assert result == "test-invalidation-id"
        call_args = mock_client.create_invalidation.call_args[1]
        assert call_args["InvalidationBatch"]["CallerReference"] == "custom-ref"

    @patch("lib.cloudfront_utils.cloudfront_client")
    @patch("lib.cloudfront_utils.time.sleep")
    def test_wait_for_invalidation_success(self, mock_sleep, mock_client):
        """Test waiting for an invalidation to complete successfully."""
        mock_client.get_invalidation.return_value = {"Invalidation": {"Status": "Completed"}}

        result = wait_for_invalidation("test-dist-id", "test-inv-id")

        assert result is True
        mock_client.get_invalidation.assert_called_once_with(DistributionId="test-dist-id", Id="test-inv-id")
        mock_sleep.assert_not_called()

    @patch("lib.cloudfront_utils.cloudfront_client")
    @patch("lib.cloudfront_utils.time.sleep")
    @patch("lib.cloudfront_utils.time.time")
    def test_wait_for_invalidation_timeout(self, mock_time, mock_sleep, mock_client):
        """Test waiting for an invalidation that times out."""
        # Mock time to exceed timeout immediately
        mock_time.side_effect = [0, 601]  # Start time, check time (after timeout)
        mock_client.get_invalidation.return_value = {"Invalidation": {"Status": "InProgress"}}

        result = wait_for_invalidation("test-dist-id", "test-inv-id", timeout=600)

        assert result is False
        # No sleep should be called because timeout is immediately exceeded
        mock_sleep.assert_not_called()

    @patch("lib.cloudfront_utils.create_cloudfront_invalidation")
    @patch("builtins.print")
    def test_invalidate_cloudfront_distributions_prod(self, mock_print, mock_create):
        """Test invalidating CloudFront distributions for production."""
        mock_create.return_value = "test-invalidation-id"

        cfg = Config(env=Environment.PROD)

        original_config = CLOUDFRONT_INVALIDATION_CONFIG[Environment.PROD]
        CLOUDFRONT_INVALIDATION_CONFIG[Environment.PROD] = [
            {
                "distribution_id": "REAL_DIST_ID",
                "domain": "test.example.com",
                "paths": ["/*"],
            }
        ]

        try:
            invalidate_cloudfront_distributions(cfg)

            mock_create.assert_called_once_with("REAL_DIST_ID", ["/*"])
            print_calls = [call[0][0] for call in mock_print.call_args_list]
            assert any("Creating CloudFront invalidations for prod" in call for call in print_calls)
            assert any("test.example.com" in call for call in print_calls)
            assert any("Invalidation created: test-invalidation-id" in call for call in print_calls)
        finally:
            CLOUDFRONT_INVALIDATION_CONFIG[Environment.PROD] = original_config

    @patch("lib.cloudfront_utils.create_cloudfront_invalidation")
    @patch("builtins.print")
    def test_invalidate_cloudfront_distributions_skip_example(self, mock_print, mock_create):
        """Test that example distribution IDs are skipped."""
        cfg = Config(env=Environment.PROD)

        original_config = CLOUDFRONT_INVALIDATION_CONFIG[Environment.PROD]
        CLOUDFRONT_INVALIDATION_CONFIG[Environment.PROD] = [
            {
                "distribution_id": "EXAMPLE_DISTRIBUTION_ID_1",
                "domain": "test.example.com",
                "paths": ["/*"],
            }
        ]

        try:
            invalidate_cloudfront_distributions(cfg)

            mock_create.assert_not_called()
            print_calls = [call[0][0] for call in mock_print.call_args_list]
            assert any("Skipping" in call and "distribution ID not configured" in call for call in print_calls)
        finally:
            CLOUDFRONT_INVALIDATION_CONFIG[Environment.PROD] = original_config

    @patch("lib.cloudfront_utils.create_cloudfront_invalidation")
    @patch("lib.cloudfront_utils.logger")
    @patch("builtins.print")
    def test_invalidate_cloudfront_distributions_error_handling(self, mock_print, mock_logger, mock_create):
        """Test error handling when creating invalidation fails."""
        mock_create.side_effect = ClientError({"Error": {"Code": "Test", "Message": "AWS error"}}, "CreateInvalidation")

        cfg = Config(env=Environment.PROD)

        original_config = CLOUDFRONT_INVALIDATION_CONFIG[Environment.PROD]
        CLOUDFRONT_INVALIDATION_CONFIG[Environment.PROD] = [
            {
                "distribution_id": "REAL_DIST_ID",
                "domain": "test.example.com",
                "paths": ["/*"],
            }
        ]

        try:
            invalidate_cloudfront_distributions(cfg)

            print_calls = [call[0][0] for call in mock_print.call_args_list]
            assert any("Failed to create invalidation:" in call for call in print_calls)
            mock_logger.error.assert_called_once()
        finally:
            CLOUDFRONT_INVALIDATION_CONFIG[Environment.PROD] = original_config

    @patch("lib.cloudfront_utils.logger")
    def test_invalidate_cloudfront_distributions_no_config(self, mock_logger):
        """Test handling of environment with no CloudFront configuration."""
        cfg = Config(env=Environment.RUNNER)  # RUNNER has empty config

        invalidate_cloudfront_distributions(cfg)

        mock_logger.info.assert_called_once_with("No CloudFront distributions configured for environment runner")

    @patch("lib.cloudfront_utils.create_cloudfront_invalidation")
    @patch("builtins.print")
    def test_invalidate_cloudfront_distributions_with_real_config(self, mock_print, mock_create):
        """Test that invalidation works with whatever configuration is present."""
        mock_create.return_value = "test-invalidation-id"

        cfg = Config(env=Environment.PROD)

        invalidate_cloudfront_distributions(cfg)

        prod_config = CLOUDFRONT_INVALIDATION_CONFIG.get(Environment.PROD, [])

        if not prod_config:
            mock_create.assert_not_called()
        else:
            expected_calls = sum(1 for config in prod_config if not config["distribution_id"].startswith("EXAMPLE_"))
            assert mock_create.call_count == expected_calls
