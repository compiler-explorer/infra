import unittest
from unittest.mock import Mock, call, patch

from click.testing import CliRunner
from lib.cli.instances import instances
from lib.env import Config, Environment


class TestInstanceIsolation(unittest.TestCase):
    """Test instance isolation and termination functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.cfg = Config(env=Environment.STAGING)

        # Create mock instance
        self.mock_instance = Mock()

        # Create mock EC2 instance object
        mock_ec2_instance = Mock()
        mock_ec2_instance.instance_id = "i-1234567890abcdef0"
        mock_ec2_instance.private_ip_address = "10.0.1.100"

        # Attach the EC2 instance to the mock instance
        self.mock_instance.instance = mock_ec2_instance
        self.mock_instance.group_arn = "arn:aws:elasticloadbalancing:us-east-1:123456789012:targetgroup/staging/abcdef"

        # Mock ASG status
        self.mock_as_status = {"AutoScalingGroupName": "staging-asg", "LifecycleState": "InService"}
        self.mock_instance.describe_autoscale.return_value = self.mock_as_status

    @patch("lib.cli.instances.pick_instance")
    @patch("lib.cli.instances.are_you_sure")
    @patch("lib.cli.instances.ec2_client")
    @patch("lib.cli.instances.as_client")
    @patch("lib.cli.instances.elb_client")
    @patch("lib.cli.instances.wait_for_autoscale_state")
    @patch("lib.cli.instances.time.sleep")
    def test_isolate_instance_success(
        self,
        mock_sleep,
        mock_wait_autoscale,
        mock_elb_client,
        mock_as_client,
        mock_ec2_client,
        mock_are_you_sure,
        mock_pick_instance,
    ):
        """Test successful instance isolation."""
        # Set up mocks
        mock_pick_instance.return_value = self.mock_instance
        mock_are_you_sure.return_value = True

        # Mock ELB deregistration response
        mock_elb_client.describe_target_health.return_value = {"TargetHealthDescriptions": []}

        # Call the function using Click's test runner
        runner = CliRunner()
        with runner.isolated_filesystem():
            result = runner.invoke(instances, ["isolate"], obj=self.cfg)

        # Verify EC2 protection calls
        mock_ec2_client.modify_instance_attribute.assert_has_calls([
            call(InstanceId="i-1234567890abcdef0", DisableApiStop={"Value": False}),
            call(InstanceId="i-1234567890abcdef0", DisableApiTermination={"Value": True}),
        ])

        # Verify ASG protection
        mock_as_client.set_instance_protection.assert_called_once_with(
            AutoScalingGroupName="staging-asg", InstanceIds=["i-1234567890abcdef0"], ProtectedFromScaleIn=True
        )

        # Verify standby
        mock_as_client.enter_standby.assert_called_once_with(
            InstanceIds=["i-1234567890abcdef0"],
            AutoScalingGroupName="staging-asg",
            ShouldDecrementDesiredCapacity=False,
        )

        # Verify deregistration
        mock_elb_client.deregister_targets.assert_called_once_with(
            TargetGroupArn="arn:aws:elasticloadbalancing:us-east-1:123456789012:targetgroup/staging/abcdef",
            Targets=[{"Id": "i-1234567890abcdef0"}],
        )

        # Verify success message printed
        assert "has been isolated successfully" in result.output

    @patch("lib.cli.instances.pick_instance")
    @patch("lib.cli.instances.are_you_sure")
    def test_isolate_instance_not_in_asg(
        self,
        mock_are_you_sure,
        mock_pick_instance,
    ):
        """Test isolation fails when instance not in ASG."""
        # Set up mocks
        self.mock_instance.describe_autoscale.return_value = None
        mock_pick_instance.return_value = self.mock_instance

        # Call the function using Click's test runner
        runner = CliRunner()
        with runner.isolated_filesystem():
            runner.invoke(instances, ["isolate"], obj=self.cfg)

        # Verify are_you_sure was not called
        mock_are_you_sure.assert_not_called()

    @patch("lib.cli.instances.pick_instance")
    @patch("lib.cli.instances.are_you_sure")
    @patch("lib.cli.instances.as_client")
    @patch("lib.cli.instances.ec2_client")
    def test_terminate_isolated_success(
        self,
        mock_ec2_client,
        mock_as_client,
        mock_are_you_sure,
        mock_pick_instance,
    ):
        """Test successful termination of isolated instance."""
        # Set up mocks
        self.mock_as_status["LifecycleState"] = "Standby"
        mock_pick_instance.return_value = self.mock_instance
        mock_are_you_sure.return_value = True

        # Call the function using Click's test runner
        runner = CliRunner()
        with runner.isolated_filesystem():
            result = runner.invoke(instances, ["terminate-isolated"], obj=self.cfg)

        # Verify protection removal
        mock_ec2_client.modify_instance_attribute.assert_has_calls([
            call(InstanceId="i-1234567890abcdef0", DisableApiTermination={"Value": False}),
            call(InstanceId="i-1234567890abcdef0", DisableApiStop={"Value": False}),
        ])

        # Verify termination
        mock_ec2_client.terminate_instances.assert_called_once_with(InstanceIds=["i-1234567890abcdef0"])

        # Verify instance was detached from ASG
        mock_as_client.detach_instances.assert_called_once_with(
            InstanceIds=["i-1234567890abcdef0"],
            AutoScalingGroupName="staging-asg",
            ShouldDecrementDesiredCapacity=False,
        )

        # Verify success message
        assert "has been terminated" in result.output

    @patch("lib.cli.instances.pick_instance")
    @patch("lib.cli.instances.are_you_sure")
    def test_terminate_isolated_wrong_state(
        self,
        mock_are_you_sure,
        mock_pick_instance,
    ):
        """Test termination fails when instance not in Standby state."""
        # Set up mocks - instance is InService, not Standby
        self.mock_as_status["LifecycleState"] = "InService"
        mock_pick_instance.return_value = self.mock_instance

        # Call the function using Click's test runner
        runner = CliRunner()
        with runner.isolated_filesystem():
            result = runner.invoke(instances, ["terminate-isolated"], obj=self.cfg)

        # Verify are_you_sure was not called
        mock_are_you_sure.assert_not_called()

        # Verify error message
        assert "not in isolated state" in result.output

    @patch("lib.cli.instances.pick_instance")
    @patch("lib.cli.instances.are_you_sure")
    @patch("lib.cli.instances.ec2_client")
    @patch("lib.cli.instances.as_client")
    @patch("lib.cli.instances.elb_client")
    @patch("lib.cli.instances.wait_for_autoscale_state")
    @patch("lib.cli.instances.time.sleep")
    def test_isolate_instance_ec2_error(
        self,
        mock_sleep,
        mock_wait_autoscale,
        mock_elb_client,
        mock_as_client,
        mock_ec2_client,
        mock_are_you_sure,
        mock_pick_instance,
    ):
        """Test isolation handles EC2 API errors gracefully."""
        # Set up mocks
        mock_pick_instance.return_value = self.mock_instance
        mock_are_you_sure.return_value = True

        # Simulate EC2 API error
        mock_ec2_client.modify_instance_attribute.side_effect = Exception("EC2 API Error")

        # Call the function using Click's test runner
        runner = CliRunner()
        with runner.isolated_filesystem():
            result = runner.invoke(instances, ["isolate"], obj=self.cfg)

        # Verify error handling
        assert result.exit_code == 1
        assert "Error isolating instance" in result.output

    @patch("lib.cli.instances.pick_instance")
    @patch("lib.cli.instances.are_you_sure")
    @patch("lib.cli.instances.ec2_client")
    @patch("lib.cli.instances.as_client")
    @patch("lib.cli.instances.elb_client")
    @patch("lib.cli.instances.wait_for_autoscale_state")
    @patch("lib.cli.instances.time.sleep")
    def test_isolate_instance_wait_for_deregistration(
        self,
        mock_sleep,
        mock_wait_autoscale,
        mock_elb_client,
        mock_as_client,
        mock_ec2_client,
        mock_are_you_sure,
        mock_pick_instance,
    ):
        """Test isolation waits for ELB deregistration to complete."""
        # Set up mocks
        mock_pick_instance.return_value = self.mock_instance
        mock_are_you_sure.return_value = True

        # Simulate deregistration in progress, then complete
        mock_elb_client.describe_target_health.side_effect = [
            {"TargetHealthDescriptions": [{"TargetHealth": {"State": "draining"}}]},
            {"TargetHealthDescriptions": [{"TargetHealth": {"State": "draining"}}]},
            {"TargetHealthDescriptions": []},
        ]

        # Call the function using Click's test runner
        runner = CliRunner()
        with runner.isolated_filesystem():
            runner.invoke(instances, ["isolate"], obj=self.cfg)

        # Verify it waited for deregistration
        assert mock_elb_client.describe_target_health.call_count == 3
        assert mock_sleep.call_count == 2


if __name__ == "__main__":
    unittest.main()
