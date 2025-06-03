"""Blue-green deployment management for Compiler Explorer."""

import signal
import sys
from typing import Any, Dict, Optional

from botocore.exceptions import ClientError

from lib.amazon import elb_client, ssm_client
from lib.aws_utils import get_asg_info, get_target_health_counts, protect_asg_capacity, reset_asg_min_size, scale_asg
from lib.ce_utils import is_running_on_admin_node
from lib.deployment_utils import (
    check_instance_health,
    print_target_group_diagnostics,
    wait_for_http_health,
    wait_for_instances_healthy,
)
from lib.env import Config


class BlueGreenDeployment:
    """Manages blue-green deployments for Compiler Explorer environments."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.env = cfg.env.value
        self.running_on_admin_node = is_running_on_admin_node()

    def _update_ssm_parameters(self, color: str, target_group_arn: str) -> None:
        """Update SSM parameters for active color and target group."""
        ssm_client.put_parameter(Name=f"/compiler-explorer/{self.env}/active-color", Value=color, Overwrite=True)
        ssm_client.put_parameter(
            Name=f"/compiler-explorer/{self.env}/active-target-group-arn", Value=target_group_arn, Overwrite=True
        )

    def get_active_color(self) -> str:
        """Get currently active color (blue/green) from Parameter Store."""
        param_name = f"/compiler-explorer/{self.env}/active-color"
        try:
            response = ssm_client.get_parameter(Name=param_name)
            return response["Parameter"]["Value"]
        except ClientError as e:
            if e.response["Error"]["Code"] == "ParameterNotFound":
                print(f"No active color parameter found for {self.env}, defaulting to 'blue'")
                return "blue"
            raise

    def get_inactive_color(self) -> str:
        """Get the inactive color based on current active color."""
        active = self.get_active_color()
        return "green" if active == "blue" else "blue"

    def get_target_group_arn(self, color: str) -> str:
        """Get target group ARN for the specified color."""
        # Construct target group name: Environment-Color (e.g., Beta-Blue, Prod-Green)
        tg_name = f"{self.env.capitalize()}-{color.capitalize()}"

        # List all target groups and find the matching one
        response = elb_client.describe_target_groups()
        for tg in response["TargetGroups"]:
            if tg["TargetGroupName"] == tg_name:
                return tg["TargetGroupArn"]

        raise ValueError(f"Target group {tg_name} not found")

    def get_asg_name(self, color: str) -> str:
        """Get ASG name for the specified color."""
        return f"{self.env}-{color}"

    def get_listener_rule_arn(self) -> Optional[str]:
        """Get the ALB listener rule ARN for this environment."""
        # For beta environment with path-based routing
        if self.env != "beta":
            return None

        # Need to find the rule that matches /beta*
        listeners = elb_client.describe_listeners(LoadBalancerArn=self._get_load_balancer_arn())

        # Find HTTPS listener
        https_listeners = [listener for listener in listeners["Listeners"] if listener["Port"] == 443]
        if not https_listeners:
            return None

        # Check rules for path pattern matching /beta*
        for listener in https_listeners:
            rules = elb_client.describe_rules(ListenerArn=listener["ListenerArn"])
            for rule in rules["Rules"]:
                conditions = rule.get("Conditions", [])
                for condition in conditions:
                    if condition.get("Field") == "path-pattern" and "/beta*" in condition.get("Values", []):
                        return rule["RuleArn"]

        return None

    def _get_load_balancer_arn(self) -> str:
        """Get the main load balancer ARN."""
        # This is the main ALB for Compiler Explorer
        response = elb_client.describe_load_balancers(Names=["GccExplorerApp"])
        return response["LoadBalancers"][0]["LoadBalancerArn"]

    def switch_target_group(self, new_color: str) -> None:
        """Switch the ALB to point to the new color's target group."""
        rule_arn = self.get_listener_rule_arn()
        if not rule_arn:
            raise ValueError(f"No listener rule found for environment {self.env}")

        new_tg_arn = self.get_target_group_arn(new_color)

        print(f"Switching {self.env} to {new_color} target group")
        elb_client.modify_rule(RuleArn=rule_arn, Actions=[{"Type": "forward", "TargetGroupArn": new_tg_arn}])

        # Update SSM parameters
        self._update_ssm_parameters(new_color, new_tg_arn)

    def get_current_capacity(self) -> int:
        """Get the current capacity of the active ASG."""
        active_color = self.get_active_color()
        asg_name = self.get_asg_name(active_color)

        asg_info = get_asg_info(asg_name)
        return asg_info["DesiredCapacity"] if asg_info else 0

    def deploy(self, target_capacity: Optional[int] = None, skip_confirmation: bool = False) -> None:
        """Perform a blue-green deployment."""
        active_color = self.get_active_color()
        inactive_color = self.get_inactive_color()

        print(f"\nStarting blue-green deployment for {self.env}")
        print(f"Active: {active_color}, Deploying to: {inactive_color}")

        # Determine target capacity
        if target_capacity is None:
            target_capacity = self.get_current_capacity()
            if target_capacity == 0:
                target_capacity = 1  # Default to 1 if nothing is running

        active_asg = self.get_asg_name(active_color)
        inactive_asg = self.get_asg_name(inactive_color)

        # Track original min sizes for cleanup
        active_original_min = None
        deployment_succeeded = False
        cleanup_handler_installed = False
        old_sigint = None
        old_sigterm = None

        # Define cleanup handler for signals
        def cleanup_on_signal(signum, frame):
            print(f"\n\n⚠️  Deployment interrupted by signal {signum}!")
            print("Performing cleanup...")
            if active_original_min is not None:
                print(f"Restoring original minimum size for {active_asg}")
                reset_asg_min_size(active_asg, min_size=active_original_min)
            print(f"Resetting minimum size of {inactive_asg}")
            reset_asg_min_size(inactive_asg, min_size=0)
            print("Cleanup complete. Exiting.")
            sys.exit(1)

        try:
            # Install signal handlers for cleanup
            old_sigint = signal.signal(signal.SIGINT, cleanup_on_signal)
            old_sigterm = signal.signal(signal.SIGTERM, cleanup_on_signal)
            cleanup_handler_installed = True
            # Step 0: Protect active ASG from scaling down during deployment
            print(f"\nStep 0: Protecting active {active_color} ASG from scale-down during deployment")
            active_original_min = protect_asg_capacity(active_asg)

            # Step 1: Scale up inactive ASG with min size protection
            print(f"\nStep 1: Scaling up {inactive_asg} to {target_capacity} instances")
            print("         Setting minimum size to prevent autoscaling interference during deployment")
            scale_asg(inactive_asg, target_capacity, set_min_size=True)

            # Step 2: Wait for instances to be in service (running)
            print(f"\nStep 2: Waiting for instances in {inactive_asg} to be in service")
            instances = wait_for_instances_healthy(inactive_asg)

            if len(instances) != target_capacity:
                raise RuntimeError(f"Expected {target_capacity} instances, but only {len(instances)} are healthy")

            # Step 3: Verify instances are healthy
            # For blue-green deployments, we can't rely on ALB target group health since
            # the inactive color isn't receiving traffic. We must use HTTP health checks.
            if self.running_on_admin_node:
                print("\nStep 3: Checking HTTP health endpoints")
                try:
                    wait_for_http_health(instances, timeout=300)  # 5 minute timeout for HTTP checks
                    print("✅ All instances are responding to health checks!")
                except TimeoutError:
                    print("⚠️  HTTP health checks timed out after 5 minutes")
                    print("This indicates instances are not properly responding to health checks")

                    # Try to get more info about what's wrong
                    tg_arn = self.get_target_group_arn(inactive_color)
                    print_target_group_diagnostics(tg_arn, instances)

                    raise RuntimeError("Instances are not passing health checks. Deployment aborted.") from None
            else:
                print("\nStep 3: Cannot verify instance health (not running on admin node)")
                print("⚠️  WARNING: Unable to verify instances are actually healthy!")
                print("Please manually verify instances are responding to health checks before proceeding.")

            # Additional confirmation when not on admin node
            if not self.running_on_admin_node and not skip_confirmation:
                print(f"\n⚠️  WARNING: About to switch traffic to {inactive_color} without HTTP health verification!")
                print("Since you're not running on the admin node, HTTP health checks were skipped.")
                print(f"Please ensure the {inactive_color} instances are responding properly before continuing.")

                response = input("\nDo you want to proceed with the traffic switch? (yes/no): ").strip().lower()
                if response not in ["yes", "y"]:
                    print("Deployment cancelled. Traffic remains on current instances.")
                    # Cleanup will happen in finally block
                    return

            # Step 4: Switch traffic to new color
            print(f"\nStep 4: Switching traffic to {inactive_color}")
            self.switch_target_group(inactive_color)

            # Step 5: Reset minimum size back to 0 now that deployment is complete
            print(f"\nStep 5: Resetting minimum size of {inactive_asg} back to 0")
            reset_asg_min_size(inactive_asg, min_size=0)

            print(f"\n✅ Blue-green deployment complete! Now serving from {inactive_color}")
            print(f"Old {active_color} ASG remains running for rollback if needed")

            deployment_succeeded = True

        finally:
            # Always restore active ASG min size, regardless of success or failure
            if active_original_min is not None:
                print(f"\nStep 6: Restoring original minimum size for {active_asg}")
                reset_asg_min_size(active_asg, min_size=active_original_min)

            # If deployment failed, also reset the inactive ASG min size
            if not deployment_succeeded:
                print(f"\nCleaning up: Resetting minimum size of {inactive_asg} after failed deployment")
                reset_asg_min_size(inactive_asg, min_size=0)

            # Restore original signal handlers
            if cleanup_handler_installed:
                signal.signal(signal.SIGINT, old_sigint)
                signal.signal(signal.SIGTERM, old_sigterm)

    def rollback(self) -> None:
        """Rollback to the previous color."""
        current_color = self.get_active_color()
        previous_color = self.get_inactive_color()

        print(f"\nRolling back from {current_color} to {previous_color}")

        # Check if previous ASG has capacity
        previous_asg = self.get_asg_name(previous_color)
        asg_info = get_asg_info(previous_asg)

        if not asg_info:
            raise ValueError(f"Previous ASG {previous_asg} not found")

        if asg_info["DesiredCapacity"] == 0:
            raise ValueError(f"Previous ASG {previous_asg} has no running instances for rollback")

        # Switch back
        self.switch_target_group(previous_color)
        print(f"Rollback complete! Now serving from {previous_color}")

    def cleanup_inactive(self) -> None:
        """Scale down the inactive ASG to save resources."""
        inactive_color = self.get_inactive_color()
        inactive_asg = self.get_asg_name(inactive_color)

        print(f"\nScaling down inactive {inactive_color} ASG")
        scale_asg(inactive_asg, 0)
        print(f"{inactive_asg} scaled to 0")

    def status(self) -> Dict[str, Any]:
        """Get the current status of blue-green deployment."""
        active_color = self.get_active_color()
        inactive_color = self.get_inactive_color()

        status: Dict[str, Any] = {
            "environment": self.env,
            "active_color": active_color,
            "inactive_color": inactive_color,
            "asgs": {},
        }

        for color in ["blue", "green"]:
            asg_name = self.get_asg_name(color)
            asg_info = get_asg_info(asg_name)

            if asg_info:
                instance_ids = [i["InstanceId"] for i in asg_info["Instances"]]

                # Get target group health
                tg_healthy_count = 0
                tg_status = "unknown"

                # Initialize HTTP health variables
                http_health_results = {}
                http_healthy_count = 0
                http_skipped = False

                if instance_ids:
                    try:
                        tg_arn = self.get_target_group_arn(color)
                        counts = get_target_health_counts(tg_arn, instance_ids)
                        healthy_count = counts["healthy"]
                        unused_count = counts["unused"]
                        tg_healthy_count = healthy_count + unused_count  # Both are "ready"

                        if healthy_count == len(instance_ids):
                            tg_status = "all_healthy"
                        elif unused_count == len(instance_ids):
                            tg_status = "all_unused"  # Ready but not receiving traffic
                        elif (healthy_count + unused_count) == len(instance_ids):
                            tg_status = "mixed_ready"  # Some healthy, some unused
                        elif tg_healthy_count > 0:
                            tg_status = "partially_healthy"
                        else:
                            tg_status = "unhealthy"
                    except Exception:
                        tg_status = "error"

                    # Get HTTP health checks for instances
                    for instance_id in instance_ids:
                        health_result = check_instance_health(instance_id, self.running_on_admin_node)
                        http_health_results[instance_id] = health_result
                        if health_result["status"] == "healthy":
                            http_healthy_count += 1
                        elif health_result["status"] == "skipped":
                            http_skipped = True

                status["asgs"][color] = {
                    "name": asg_name,
                    "desired": asg_info["DesiredCapacity"],
                    "min": asg_info["MinSize"],
                    "max": asg_info["MaxSize"],
                    "instances": len(asg_info["Instances"]),
                    "healthy_instances": len([i for i in asg_info["Instances"] if i["HealthStatus"] == "Healthy"]),
                    "target_group_healthy": tg_healthy_count,
                    "target_group_status": tg_status,
                    "http_health_results": http_health_results,
                    "http_healthy_count": http_healthy_count,
                    "http_skipped": http_skipped,
                }
            else:
                status["asgs"][color] = {"error": "ASG not found"}

        return status
