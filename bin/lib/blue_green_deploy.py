"""Blue-green deployment management for Compiler Explorer."""

from __future__ import annotations

import logging
import signal
import sys
from typing import Any

from botocore.exceptions import ClientError

from lib.amazon import elb_client, get_current_key, set_current_key, ssm_client
from lib.aws_utils import (
    get_asg_info,
    get_instance_private_ip,
    get_target_health_counts,
    protect_asg_capacity,
    reset_asg_min_size,
    restore_asg_capacity_protection,
    scale_asg,
)
from lib.builds_core import (
    check_compiler_discovery,
    get_release_without_discovery_check,
    set_version_for_deployment,
)
from lib.ce_utils import is_running_on_admin_node
from lib.compiler_routing import update_compiler_routing_table
from lib.deployment_utils import (
    check_instance_health,
    clear_router_cache,
    print_target_group_diagnostics,
    wait_for_compiler_registration,
    wait_for_http_health,
    wait_for_instances_healthy,
)
from lib.discovery import copy_discovery_to_prod, discovery_exists
from lib.env import Config

LOGGER = logging.getLogger(__name__)


class DeploymentCancelledException(Exception):
    """Exception raised when a deployment is cancelled by the user."""

    pass


class BlueGreenDeployment:
    """Manages blue-green deployments for Compiler Explorer environments."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.env = cfg.env.value
        self.running_on_admin_node = is_running_on_admin_node()

        # Deployment state for signal handling
        self._deployment_state: dict[str, Any] = {
            "active_asg": None,
            "inactive_asg": None,
            "active_original_min": None,
            "active_original_max": None,
            "in_deployment": False,
            "original_version_key": None,
            "version_was_changed": False,
        }

    def _cleanup_on_signal(self, signum, frame):
        """Handle cleanup when deployment is interrupted by a signal."""
        if not self._deployment_state["in_deployment"]:
            # Not in a deployment, just exit
            sys.exit(1)

        LOGGER.warning(f"\n\nDeployment interrupted by signal {signum}!")
        print("Performing cleanup...")

        active_asg = self._deployment_state["active_asg"]
        inactive_asg = self._deployment_state["inactive_asg"]
        active_original_min = self._deployment_state["active_original_min"]
        active_original_max = self._deployment_state["active_original_max"]
        original_version_key = self._deployment_state.get("original_version_key")
        version_was_changed = self._deployment_state.get("version_was_changed", False)

        if active_original_min is not None and active_original_max is not None and active_asg:
            print(f"Restoring original capacity settings for {active_asg}")
            try:
                restore_asg_capacity_protection(active_asg, active_original_min, active_original_max)
            except ClientError as e:
                LOGGER.warning(f"Failed to restore capacity settings for {active_asg}: {e}")

        if inactive_asg:
            # Reset to 0 since deployment was interrupted (inactive ASG)
            print(f"Resetting minimum size of {inactive_asg} to 0")
            try:
                reset_asg_min_size(inactive_asg, min_size=0)
            except ClientError as e:
                LOGGER.warning(f"Failed to reset min size for {inactive_asg}: {e}")

        # Rollback version if it was changed
        if version_was_changed and original_version_key:
            print(f"Rolling back version to {original_version_key}")
            try:
                set_current_key(self.cfg, original_version_key)
                print("✓ Version rolled back successfully")
            except ClientError as e:
                LOGGER.error(f"Failed to rollback version: {e}")
                LOGGER.error(f"You may need to manually set version back to {original_version_key}")

        print("Cleanup complete. Exiting.")
        sys.exit(1)

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
                LOGGER.warning(f"No active color parameter found for {self.env}, defaulting to 'blue'")
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

    def get_listener_rule_arn(self) -> str | None:
        """Get the ALB listener rule ARN for this environment."""
        # Get listeners for the load balancer
        listeners = elb_client.describe_listeners(LoadBalancerArn=self._get_load_balancer_arn())

        # Find HTTPS listener
        https_listeners = [listener for listener in listeners["Listeners"] if listener["Port"] == 443]
        if not https_listeners:
            return None

        # For production, we return the listener ARN itself (to modify default action)
        if not self.cfg.env.path_pattern:
            return https_listeners[0]["ListenerArn"]

        # For other environments, find the specific rule for their path pattern
        target_pattern = self.cfg.env.path_pattern
        # Check rules for path pattern matching
        for listener in https_listeners:
            rules = elb_client.describe_rules(ListenerArn=listener["ListenerArn"])
            for rule in rules["Rules"]:
                conditions = rule.get("Conditions", [])
                for condition in conditions:
                    if condition.get("Field") == "path-pattern" and target_pattern in condition.get("Values", []):
                        return rule["RuleArn"]

        return None

    def _get_load_balancer_arn(self) -> str:
        """Get the main load balancer ARN."""
        # This is the main ALB for Compiler Explorer
        response = elb_client.describe_load_balancers(Names=["GccExplorerApp"])
        return response["LoadBalancers"][0]["LoadBalancerArn"]

    def switch_target_group(self, new_color: str) -> None:
        """Switch the ALB to point to the new color's target group."""
        rule_or_listener_arn = self.get_listener_rule_arn()
        if not rule_or_listener_arn:
            raise ValueError(f"No listener rule/listener found for environment {self.env}")

        new_tg_arn = self.get_target_group_arn(new_color)

        print(f"Switching {self.env} to {new_color} target group")

        if self.env == "prod":
            # For production, modify both HTTP and HTTPS listeners' default actions
            listeners = elb_client.describe_listeners(LoadBalancerArn=self._get_load_balancer_arn())

            for listener in listeners["Listeners"]:
                if listener["Port"] in [80, 443]:
                    LOGGER.debug(f"  Updating {listener['Protocol']} listener on port {listener['Port']}")
                    elb_client.modify_listener(
                        ListenerArn=listener["ListenerArn"],
                        DefaultActions=[{"Type": "forward", "TargetGroupArn": new_tg_arn}],
                    )
        else:
            # For beta (and other environments with rules), modify the rule
            elb_client.modify_rule(
                RuleArn=rule_or_listener_arn, Actions=[{"Type": "forward", "TargetGroupArn": new_tg_arn}]
            )

        # Update SSM parameters
        self._update_ssm_parameters(new_color, new_tg_arn)

    def get_current_capacity(self) -> int:
        """Get the current capacity of the active ASG."""
        active_color = self.get_active_color()
        asg_name = self.get_asg_name(active_color)

        asg_info = get_asg_info(asg_name)
        return asg_info["DesiredCapacity"] if asg_info else 0

    @staticmethod
    def _display_discovery_status(version: str) -> None:
        """Display discovery status for the target version across environments."""
        print(f"\nDiscovery status for {version}:")
        for env in ["prod", "staging", "beta"]:
            exists = discovery_exists(env, version)
            label = "found" if exists else "not found"
            padded_env = f"{env}:"
            print(f"  {padded_env:10s} {label}")

    def _copy_and_check_discovery(self, source_env: str, version: str, branch: str | None):
        """Copy discovery from source environment and return release."""
        print(f"Attempting to copy discovery from {source_env} for version {version}...")
        try:
            if copy_discovery_to_prod(source_env, version):
                print("Retrying discovery check...")
                try:
                    release = check_compiler_discovery(self.cfg, version, branch)
                    if release:
                        return release
                except RuntimeError:
                    pass
                LOGGER.warning("Discovery copy succeeded but check still failed. Continuing anyway.")
            else:
                LOGGER.warning(f"No discovery file found in {source_env} for this version.")
                LOGGER.warning("Falling back to continuing without discovery.")

            release = get_release_without_discovery_check(self.cfg, version, branch)
            if not release:
                raise RuntimeError(f"Version {version} not found") from None
            return release
        except (ClientError, OSError) as copy_error:
            LOGGER.error(f"Failed to copy discovery file: {copy_error}")
            LOGGER.error("Deployment cancelled due to discovery copy failure.")
            raise DeploymentCancelledException("Discovery copy failed") from copy_error

    def _handle_prod_missing_discovery(self, error: RuntimeError, version: str, branch: str | None):
        """Handle missing prod discovery by checking staging/beta and presenting options."""
        staging_has_discovery = discovery_exists("staging", version)
        beta_has_discovery = discovery_exists("beta", version)

        LOGGER.warning("%s", error)

        if staging_has_discovery:
            print("Staging discovery IS available for this version.")
            print("Options:")
            print("  1. Copy discovery from staging (recommended)")
            print("  2. Continue without discovery")
            print("  3. Cancel deployment")
        elif beta_has_discovery:
            print("Beta discovery IS available (staging is not).")
            print("Options:")
            print("  1. Copy discovery from beta")
            print("  2. Continue without discovery")
            print("  3. Cancel deployment")
        else:
            print("WARNING: No discovery found in staging or beta for this version either.")
            suggestion = f"ce workflows run-discovery {version} --environment staging"
            print(f"You may need to run discovery first: {suggestion}")
            print("Options:")
            print("  1. Continue without discovery (risky)")
            print("  2. Cancel deployment")

        source_env = "staging" if staging_has_discovery else ("beta" if beta_has_discovery else None)

        while True:
            if source_env:
                response = input("Choose option (1/2/3): ").strip()
                if response == "1":
                    return self._copy_and_check_discovery(source_env, version, branch)
                elif response == "2":
                    LOGGER.warning("Continuing without discovery...")
                    release = get_release_without_discovery_check(self.cfg, version, branch)
                    if not release:
                        raise RuntimeError(f"Version {version} not found") from None
                    return release
                elif response == "3":
                    print("Deployment cancelled.")
                    raise DeploymentCancelledException("Deployment cancelled by user") from None
                else:
                    LOGGER.error("Invalid option. Please choose 1, 2, or 3.")
            else:
                response = input("Choose option (1/2): ").strip()
                if response == "1":
                    LOGGER.warning("Continuing without discovery...")
                    release = get_release_without_discovery_check(self.cfg, version, branch)
                    if not release:
                        raise RuntimeError(f"Version {version} not found") from None
                    return release
                elif response == "2":
                    print("Deployment cancelled.")
                    raise DeploymentCancelledException("Deployment cancelled by user") from None
                else:
                    LOGGER.error("Invalid option. Please choose 1 or 2.")

    def deploy(
        self,
        target_capacity: int | None = None,
        skip_confirmation: bool = False,
        version: str | None = None,
        branch: str | None = None,
        ignore_hash_mismatch: bool = False,
        skip_compiler_check: bool = False,
        compiler_timeout: int = 600,
    ) -> None:
        """Perform a blue-green deployment with optional version setting."""
        active_color = self.get_active_color()
        inactive_color = self.get_inactive_color()

        print(f"\nStarting blue-green deployment for {self.env}")
        print(f"Active: {active_color}, Deploying to: {inactive_color}")

        # Determine target capacity
        if target_capacity is None:
            target_capacity = self.get_current_capacity()
            if target_capacity == 0:
                target_capacity = max(1, self.cfg.env.min_instances)  # Use environment's minimum instances

        active_asg = self.get_asg_name(active_color)
        inactive_asg = self.get_asg_name(inactive_color)

        # Check if inactive ASG already has instances running
        inactive_asg_info = get_asg_info(inactive_asg)
        if inactive_asg_info and inactive_asg_info["DesiredCapacity"] > 0:
            LOGGER.warning(
                f"\nThe {inactive_color} ASG already has {inactive_asg_info['DesiredCapacity']} instance(s) running!"
            )
            LOGGER.warning("This means you'll be switching to existing instances rather than deploying fresh ones.")
            print("\nIf you want to:")
            print(
                f"  • Switch traffic to existing {inactive_color} instances → use 'ce --env {self.env} blue-green switch'"
            )
            print(f"  • Roll back to {inactive_color} → use 'ce --env {self.env} blue-green rollback'")
            print(f"  • Deploy fresh instances → run 'ce --env {self.env} blue-green cleanup' first, then deploy")

            if skip_confirmation:
                LOGGER.error("\nDeployment cancelled (--skip-confirmation prevents deploying to existing instances).")
                LOGGER.error("Use one of the commands above instead.")
                raise DeploymentCancelledException(
                    "Deployment cancelled: existing instances found with --skip-confirmation"
                )
            else:
                response = (
                    input(
                        f"\nDo you want to continue with deployment to existing {inactive_color} instances? (yes/no): "
                    )
                    .strip()
                    .lower()
                )
                if response not in ["yes", "y"]:
                    print("Deployment cancelled.")
                    raise DeploymentCancelledException("Deployment cancelled by user")

        # Track original min sizes for cleanup
        active_original_min = None
        deployment_succeeded = False
        cleanup_handler_installed = False
        old_sigint = None
        old_sigterm = None
        original_version_key = None
        version_was_changed = False

        # Update deployment state for signal handler
        self._deployment_state.update({
            "active_asg": active_asg,
            "inactive_asg": inactive_asg,
            "active_original_min": None,  # Will be set after protection
            "active_original_max": None,  # Will be set after protection
            "in_deployment": True,
            "original_version_key": None,
            "version_was_changed": False,
        })

        # Install signal handlers for cleanup
        old_sigint = signal.signal(signal.SIGINT, self._cleanup_on_signal)
        old_sigterm = signal.signal(signal.SIGTERM, self._cleanup_on_signal)
        cleanup_handler_installed = True

        # Step 0: Protect active ASG from scaling during deployment
        print(f"\nStep 0: Protecting active {active_color} ASG from scaling during deployment")
        protection_result = protect_asg_capacity(active_asg)
        if protection_result:
            active_original_min, active_original_max = protection_result
            # Update deployment state with the original sizes
            self._deployment_state["active_original_min"] = active_original_min
            self._deployment_state["active_original_max"] = active_original_max
        else:
            active_original_min, active_original_max = None, None

        try:
            # Step 0.5: Set version after ASG is protected but before scaling
            if version:
                # Get current version first for potential rollback
                original_version_key = get_current_key(self.cfg)

                print(f"\nStep 0.5: Setting build version to {version}")
                print(f"         (Current version: {original_version_key})")
                self._display_discovery_status(version)

                # Check if version exists and has discovery
                try:
                    release = check_compiler_discovery(self.cfg, version, branch)
                    if not release:
                        raise RuntimeError(f"Version {version} not found")
                except RuntimeError as e:
                    # Discovery hasn't run - handle specially for prod deployments
                    if self.cfg.env.value == "prod":
                        if skip_confirmation:
                            LOGGER.warning(f"{e}")
                            LOGGER.error(
                                "--skip-confirmation cannot be used for production deployments without discovery."
                            )
                            LOGGER.error("Production deployments require either:")
                            LOGGER.error("  1. Existing discovery file for the version")
                            LOGGER.error("  2. Manual confirmation to copy discovery from staging")
                            print("Deployment cancelled.")
                            raise DeploymentCancelledException(
                                "Production deployments require manual confirmation"
                            ) from None
                        release = self._handle_prod_missing_discovery(e, version, branch)
                    elif skip_confirmation:
                        # For non-prod environments, skip_confirmation is allowed
                        LOGGER.warning("%s", e)
                        LOGGER.warning("Proceeding anyway due to --skip-confirmation")
                        release = get_release_without_discovery_check(self.cfg, version, branch)
                        if not release:
                            raise RuntimeError(f"Version {version} not found") from None
                    else:
                        LOGGER.warning("%s", e)
                        response = input("Are you sure you want to continue? (yes/no): ").strip().lower()
                        if response not in ["yes", "y"]:
                            print("Version setting cancelled.")
                            raise DeploymentCancelledException("Version setting cancelled by user") from None
                        release = get_release_without_discovery_check(self.cfg, version, branch)
                        if not release:
                            raise RuntimeError(f"Version {version} not found") from None

                if not set_version_for_deployment(self.cfg, release, ignore_hash_mismatch=ignore_hash_mismatch):
                    raise RuntimeError(f"Failed to set version {version}")

                version_was_changed = True
                self._deployment_state["original_version_key"] = original_version_key
                self._deployment_state["version_was_changed"] = True

                print(f"✓ Version {version} set successfully")
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
                    LOGGER.error("HTTP health checks timed out after 5 minutes")
                    LOGGER.error("This indicates instances are not properly responding to health checks")

                    # Try to get more info about what's wrong
                    tg_arn = self.get_target_group_arn(inactive_color)
                    print_target_group_diagnostics(tg_arn, instances)

                    raise RuntimeError("Instances are not passing health checks. Deployment aborted.") from None
            else:
                LOGGER.warning("\nStep 3: Cannot verify instance health (not running on admin node)")
                LOGGER.warning("Unable to verify instances are actually healthy!")
                LOGGER.warning("Please manually verify instances are responding to health checks before proceeding.")

            # Additional confirmation when not on admin node
            if not self.running_on_admin_node and not skip_confirmation:
                LOGGER.warning(f"\nAbout to switch traffic to {inactive_color} without HTTP health verification!")
                LOGGER.warning("Since you're not running on the admin node, HTTP health checks were skipped.")
                LOGGER.warning(
                    f"Please ensure the {inactive_color} instances are responding properly before continuing."
                )

                response = input("\nDo you want to proceed with the traffic switch? (yes/no): ").strip().lower()
                if response not in ["yes", "y"]:
                    print("Deployment cancelled. Traffic remains on current instances.")
                    # Cleanup will happen in finally block
                    return

            # Step 3.5: Check compiler registration (unless skipped)
            if not skip_compiler_check:
                print("\nStep 3.5: Checking compiler registration and discovery")
                try:
                    wait_for_compiler_registration(instances, self.env, timeout=compiler_timeout)
                    print("✅ All instances have completed compiler registration!")
                except TimeoutError:
                    LOGGER.error("Compiler registration check timed out")
                    LOGGER.error("Instances may not be ready to handle compilation requests")

                    if skip_confirmation:
                        LOGGER.error("Deployment aborted due to compiler registration timeout")
                        raise RuntimeError("Compiler registration timeout") from None
                    else:
                        LOGGER.warning("Do you want to proceed anyway? Instances may not be fully ready.")
                        response = input("Continue with deployment? (yes/no): ").strip().lower()
                        if response not in ["yes", "y"]:
                            print("Deployment cancelled due to compiler registration issues.")
                            return
            else:
                print("\nStep 3.5: Skipping compiler registration check (--skip-compiler-check)")

            # Step 3.9: Clear router cache before traffic switch
            print("\nStep 3.9: Clearing router cache before traffic switch")
            if clear_router_cache(self.env):
                print("✓ Router cache cleared successfully")
            else:
                LOGGER.warning("Failed to clear router cache (deployment will continue, cache expires in 30s)")

            # Step 4: Switch traffic to new color
            print(f"\nStep 4: Switching traffic to {inactive_color}")
            self.switch_target_group(inactive_color)

            # Step 5: Reset minimum size to 1 to ensure ASG always has at least one instance
            # This ensures the active ASG is always ready, regardless of environment defaults
            min_size_after_deploy = max(1, self.cfg.env.min_instances)
            print(
                f"\nStep 5: Resetting minimum size of {inactive_asg} to {min_size_after_deploy} (ensuring at least 1)"
            )
            reset_asg_min_size(inactive_asg, min_size=min_size_after_deploy)

            # Step 5.5: Reset old active ASG minimum size to 0 (it's now inactive)
            print(f"\nStep 5.5: Resetting minimum size of {active_asg} to 0 (now inactive)")
            reset_asg_min_size(active_asg, min_size=0)

            # Step 6: Update compiler routing table
            print(f"\nStep 6: Updating compiler routing table for {self.env}")
            try:
                # Get private IPs of new instances to query directly (bypassing ALB propagation delay)
                instance_ips = []
                for instance_id in instances:
                    private_ip = get_instance_private_ip(instance_id)
                    if private_ip:
                        instance_ips.append(private_ip)

                if instance_ips:
                    print("  Querying compiler list directly from new instances (bypassing ALB)")
                    result = update_compiler_routing_table(self.env, instance_ips=instance_ips)
                else:
                    print("  Warning: No instance IPs found, falling back to public API")
                    result = update_compiler_routing_table(self.env)

                print(
                    f"  Compiler routing updated: {result['added']} added, {result['updated']} updated, {result['deleted']} deleted"
                )
            except ClientError as e:
                LOGGER.warning(f"Failed to update compiler routing table: {e}")
                LOGGER.warning("Deployment will continue, but compiler routing may be out of date")
                print(f"  ⚠️  Warning: Compiler routing update failed: {e}")

            print(f"\n✅ Blue-green deployment complete! Now serving from {inactive_color}")
            print(f"Old {active_color} ASG remains running for rollback if needed")

            deployment_succeeded = True

        finally:
            # Always restore active ASG capacity settings, regardless of success or failure
            if active_original_min is not None and active_original_max is not None:
                print(f"\nStep 7: Restoring original capacity settings for {active_asg}")
                restore_asg_capacity_protection(active_asg, active_original_min, active_original_max)

            # If deployment failed, also reset the inactive ASG min size
            if not deployment_succeeded:
                # Use 0 for failed deployments since it's still inactive
                print(f"\nCleaning up: Resetting minimum size of {inactive_asg} to 0 after failed deployment")
                reset_asg_min_size(inactive_asg, min_size=0)

                # Rollback version if it was changed
                if version_was_changed and original_version_key:
                    print(f"\nRolling back version to {original_version_key}")
                    try:
                        set_current_key(self.cfg, original_version_key)
                        print("✓ Version rolled back successfully")
                    except ClientError as e:
                        LOGGER.error(f"Failed to rollback version: {e}")
                        LOGGER.error(f"You may need to manually set version back to {original_version_key}")

            # Restore original signal handlers
            if cleanup_handler_installed:
                signal.signal(signal.SIGINT, old_sigint)
                signal.signal(signal.SIGTERM, old_sigterm)

            # Clear deployment state
            self._deployment_state = {
                "active_asg": None,
                "inactive_asg": None,
                "active_original_min": None,
                "active_original_max": None,
                "in_deployment": False,
                "original_version_key": None,
                "version_was_changed": False,
            }

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
        # First reset minimum size to 0 to allow scaling down
        print(f"Resetting minimum size of {inactive_asg} to 0")
        reset_asg_min_size(inactive_asg, min_size=0)
        # Then scale down to 0 instances
        print(f"Scaling {inactive_asg} to 0 instances")
        scale_asg(inactive_asg, 0)
        print(f"{inactive_asg} scaled to 0")

    def status(self) -> dict[str, Any]:
        """Get the current status of blue-green deployment."""
        active_color = self.get_active_color()
        inactive_color = self.get_inactive_color()

        status: dict[str, Any] = {
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
                    except ClientError:
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
