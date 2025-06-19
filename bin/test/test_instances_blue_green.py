"""Tests for blue-green deployment support in instances.py."""

import unittest
from unittest.mock import MagicMock, patch

from lib.cli.instances import get_instances_for_environment
from lib.env import Config, Environment


class TestBlueGreenInstances(unittest.TestCase):
    """Test blue-green deployment support for instance operations."""

    def test_get_instances_blue_green_environment(self):
        """Test getting instances for environments with blue-green support."""
        cfg = Config(env=Environment.PROD)
        
        with patch("lib.blue_green_deploy.BlueGreenDeployment") as mock_deployment_class:
            mock_deployment = MagicMock()
            mock_deployment_class.return_value = mock_deployment
            mock_deployment.get_active_color.return_value = "blue"
            mock_deployment.get_target_group_arn.return_value = "arn:aws:targetgroup/Prod-Blue/123"
            
            with patch("lib.cli.instances.Instance") as mock_instance:
                mock_instances = [MagicMock(), MagicMock()]
                mock_instance.elb_instances.return_value = mock_instances
                
                result = get_instances_for_environment(cfg)
                
                self.assertEqual(result, mock_instances)
                mock_deployment.get_active_color.assert_called_once()
                mock_deployment.get_target_group_arn.assert_called_once_with("blue")
                mock_instance.elb_instances.assert_called_once_with("arn:aws:targetgroup/Prod-Blue/123")

    def test_get_instances_legacy_environment(self):
        """Test getting instances for environments without blue-green support."""
        cfg = Config(env=Environment.STAGING)
        
        with patch("lib.cli.instances.target_group_arn_for") as mock_tg_arn:
            mock_tg_arn.return_value = "arn:aws:targetgroup/Staging/456"
            
            with patch("lib.cli.instances.Instance") as mock_instance:
                mock_instances = [MagicMock()]
                mock_instance.elb_instances.return_value = mock_instances
                
                result = get_instances_for_environment(cfg)
                
                self.assertEqual(result, mock_instances)
                mock_tg_arn.assert_called_once_with(cfg)
                mock_instance.elb_instances.assert_called_once_with("arn:aws:targetgroup/Staging/456")

    def test_get_instances_blue_green_fallback(self):
        """Test fallback to legacy when blue-green lookup fails."""
        cfg = Config(env=Environment.PROD)
        
        with patch("lib.blue_green_deploy.BlueGreenDeployment") as mock_deployment_class:
            # Simulate blue-green deployment failure
            mock_deployment_class.side_effect = Exception("Parameter not found")
            
            with patch("lib.cli.instances.target_group_arn_for") as mock_tg_arn:
                mock_tg_arn.return_value = "arn:aws:targetgroup/Prod/789"
                
                with patch("lib.cli.instances.Instance") as mock_instance:
                    mock_instances = [MagicMock()]
                    mock_instance.elb_instances.return_value = mock_instances
                    
                    result = get_instances_for_environment(cfg)
                    
                    self.assertEqual(result, mock_instances)
                    mock_tg_arn.assert_called_once_with(cfg)
                    mock_instance.elb_instances.assert_called_once_with("arn:aws:targetgroup/Prod/789")

    def test_beta_uses_blue_green(self):
        """Test that beta environment also uses blue-green deployment."""
        cfg = Config(env=Environment.BETA)
        
        with patch("lib.blue_green_deploy.BlueGreenDeployment") as mock_deployment_class:
            mock_deployment = MagicMock()
            mock_deployment_class.return_value = mock_deployment
            mock_deployment.get_active_color.return_value = "green"
            mock_deployment.get_target_group_arn.return_value = "arn:aws:targetgroup/Beta-Green/abc"
            
            with patch("lib.cli.instances.Instance") as mock_instance:
                mock_instances = [MagicMock()]
                mock_instance.elb_instances.return_value = mock_instances
                
                result = get_instances_for_environment(cfg)
                
                self.assertEqual(result, mock_instances)
                mock_deployment.get_active_color.assert_called_once()
                mock_deployment.get_target_group_arn.assert_called_once_with("green")


if __name__ == "__main__":
    unittest.main()