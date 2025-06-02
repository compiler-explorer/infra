"""Blue-green deployment management for Compiler Explorer."""

import time
from typing import Any, Dict, List, Optional

import requests
from botocore.exceptions import ClientError

from lib.amazon import as_client, ec2_client, elb_client, ssm_client
from lib.ce_utils import is_running_on_admin_node
from lib.env import Config


class BlueGreenDeployment:
    """Manages blue-green deployments for Compiler Explorer environments."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.env = cfg.env.value
        self.running_on_admin_node = is_running_on_admin_node()

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
        # For beta, we have specific blue/green target groups
        if self.env == "beta":
            tg_name = f"Beta-{color.capitalize()}"
        else:
            # For other environments, construct the name
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
        if self.env == "beta":
            # Need to find the rule that matches /beta*
            listeners = elb_client.describe_listeners(LoadBalancerArn=self._get_load_balancer_arn())

            for listener in listeners["Listeners"]:
                if listener["Port"] == 443:  # HTTPS listener
                    rules = elb_client.describe_rules(ListenerArn=listener["ListenerArn"])
                    for rule in rules["Rules"]:
                        if rule.get("Conditions"):
                            for condition in rule["Conditions"]:
                                if condition.get("Field") == "path-pattern" and "/beta*" in condition.get("Values", []):
                                    return rule["RuleArn"]

        return None

    def _get_load_balancer_arn(self) -> str:
        """Get the main load balancer ARN."""
        # This is the main ALB for Compiler Explorer
        response = elb_client.describe_load_balancers(Names=["GccExplorerApp"])
        return response["LoadBalancers"][0]["LoadBalancerArn"]

    def wait_for_instances_healthy(self, asg_name: str, timeout: int = 900) -> List[str]:
        """Wait for all instances in ASG to be healthy."""
        start_time = time.time()
        last_status_time = 0.0

        print(f"Waiting for instances in {asg_name} to become healthy (this typically takes 5-10 minutes)...")

        # Don't check for the first 30 seconds - instances need time to boot
        print("Initial boot period (30s)...")
        time.sleep(30)

        while time.time() - start_time < timeout:
            try:
                response = as_client.describe_auto_scaling_groups(AutoScalingGroupNames=[asg_name])

                if not response["AutoScalingGroups"]:
                    raise ValueError(f"ASG {asg_name} not found")

                asg = response["AutoScalingGroups"][0]
                desired = asg["DesiredCapacity"]

                if desired == 0:
                    print(f"ASG {asg_name} has desired capacity of 0")
                    return []

                healthy_instances = [
                    i["InstanceId"]
                    for i in asg["Instances"]
                    if i["HealthStatus"] == "Healthy" and i["LifecycleState"] == "InService"
                ]

                current_time = time.time()

                if len(healthy_instances) == desired:
                    elapsed_mins = int((current_time - start_time) / 60)
                    elapsed_secs = int((current_time - start_time) % 60)
                    print(f"✅ All {desired} instances healthy after {elapsed_mins}m {elapsed_secs}s")

                    # Print full status when all instances are healthy
                    print("Instance details:")
                    for instance in asg["Instances"]:
                        iid = instance["InstanceId"]
                        health = instance["HealthStatus"]
                        state = instance["LifecycleState"]
                        print(f"  {iid}: {health}, {state}")

                    return healthy_instances

                # Only print status every 60 seconds to reduce noise
                if current_time - last_status_time >= 60:
                    elapsed_mins = int((current_time - start_time) / 60)
                    print(f"[{elapsed_mins}m] ASG {asg_name}: {len(healthy_instances)}/{desired} instances healthy")
                    last_status_time = current_time

            except ClientError as e:
                print(f"Error checking ASG health: {e}")

            time.sleep(30)  # Check every 30 seconds instead of 10

        raise TimeoutError(f"Timeout waiting for instances in {asg_name} to become healthy")

    def wait_for_targets_healthy(self, target_group_arn: str, instance_ids: List[str], timeout: int = 600) -> List[str]:
        """Wait for instances to become healthy in the target group."""
        if not instance_ids:
            return []

        start_time = time.time()
        last_status_time = 0.0

        print(f"Waiting for {len(instance_ids)} instances to become healthy in target group...")

        while time.time() - start_time < timeout:
            response = elb_client.describe_target_health(
                TargetGroupArn=target_group_arn, Targets=[{"Id": iid} for iid in instance_ids]
            )

            healthy = []
            unhealthy = []

            for target in response["TargetHealthDescriptions"]:
                if target["TargetHealth"]["State"] == "healthy":
                    healthy.append(target["Target"]["Id"])
                else:
                    unhealthy.append(
                        {
                            "id": target["Target"]["Id"],
                            "state": target["TargetHealth"]["State"],
                            "reason": target["TargetHealth"].get("Reason", "Unknown"),
                        }
                    )

            current_time = time.time()

            if len(healthy) == len(instance_ids):
                elapsed_mins = int((current_time - start_time) / 60)
                elapsed_secs = int((current_time - start_time) % 60)
                print(f"✅ All {len(instance_ids)} targets healthy after {elapsed_mins}m {elapsed_secs}s")

                # Print full status when all targets are healthy
                print("Target health details:")
                for target in response["TargetHealthDescriptions"]:
                    iid = target["Target"]["Id"]
                    state = target["TargetHealth"]["State"]
                    print(f"  {iid}: {state}")

                return healthy

            # Only print status every 30 seconds to reduce noise
            if current_time - last_status_time >= 30:
                elapsed_mins = int((current_time - start_time) / 60)
                print(f"[{elapsed_mins}m] Target group health: {len(healthy)}/{len(instance_ids)} healthy")

                # Only show detailed unhealthy info occasionally to reduce noise
                if unhealthy and current_time - last_status_time >= 60:
                    print(f"  Unhealthy targets: {[f'{u["id"]}: {u["state"]}' for u in unhealthy[:3]]}")
                    if len(unhealthy) > 3:
                        print(f"  ... and {len(unhealthy) - 3} more")

                last_status_time = current_time

            time.sleep(15)  # Check every 15 seconds instead of 5

        raise TimeoutError("Timeout waiting for targets to become healthy")

    def wait_for_http_health(self, instance_ids: List[str], timeout: int = 300) -> List[str]:
        """Wait for instances to respond healthy to HTTP health checks."""
        if not instance_ids:
            return []

        start_time = time.time()
        last_status_time = 0.0

        print(f"Testing HTTP health for {len(instance_ids)} instances...")

        while time.time() - start_time < timeout:
            healthy_instances = []
            unhealthy_instances = []

            for instance_id in instance_ids:
                health_result = self.check_instance_health(instance_id)
                if health_result["status"] == "healthy":
                    healthy_instances.append(instance_id)
                else:
                    unhealthy_instances.append(
                        {
                            "id": instance_id,
                            "status": health_result["status"],
                            "message": health_result.get("message", "Unknown error"),
                        }
                    )

            current_time = time.time()

            if len(healthy_instances) == len(instance_ids):
                elapsed_secs = int(current_time - start_time)
                print(f"✅ All {len(instance_ids)} instances responding to HTTP health checks after {elapsed_secs}s")
                return healthy_instances

            # Only print status every 10 seconds to reduce noise
            if current_time - last_status_time >= 10:
                elapsed_secs = int(current_time - start_time)
                print(f"[{elapsed_secs}s] HTTP health: {len(healthy_instances)}/{len(instance_ids)} healthy")
                last_status_time = current_time

            time.sleep(5)  # Keep checking every 5 seconds since HTTP checks are faster

        raise TimeoutError(f"Timeout waiting for HTTP health checks to pass for {len(instance_ids)} instances")

    def scale_asg(self, asg_name: str, desired_capacity: int) -> None:
        """Scale an ASG to the specified capacity."""
        print(f"Scaling {asg_name} to {desired_capacity} instances")
        as_client.set_desired_capacity(AutoScalingGroupName=asg_name, DesiredCapacity=desired_capacity)

    def switch_target_group(self, new_color: str) -> None:
        """Switch the ALB to point to the new color's target group."""
        rule_arn = self.get_listener_rule_arn()
        if not rule_arn:
            raise ValueError(f"No listener rule found for environment {self.env}")

        new_tg_arn = self.get_target_group_arn(new_color)

        print(f"Switching {self.env} to {new_color} target group")
        elb_client.modify_rule(RuleArn=rule_arn, Actions=[{"Type": "forward", "TargetGroupArn": new_tg_arn}])

        # Update SSM parameters
        ssm_client.put_parameter(Name=f"/compiler-explorer/{self.env}/active-color", Value=new_color, Overwrite=True)
        ssm_client.put_parameter(
            Name=f"/compiler-explorer/{self.env}/active-target-group-arn", Value=new_tg_arn, Overwrite=True
        )

    def check_instance_health(self, instance_id: str) -> Dict[str, Any]:
        """Check the health of an instance by testing its /healthcheck endpoint."""
        if not self.running_on_admin_node:
            return {
                "status": "skipped",
                "message": "HTTP health checks only available from admin node",
                "hostname": "local-machine",
            }

        try:
            # Get instance private IP
            response = ec2_client.describe_instances(InstanceIds=[instance_id])
            if not response["Reservations"] or not response["Reservations"][0]["Instances"]:
                return {"status": "error", "message": "Instance not found"}

            instance = response["Reservations"][0]["Instances"][0]
            if instance["State"]["Name"] != "running":
                return {"status": "error", "message": f"Instance state: {instance['State']['Name']}"}

            private_ip = instance.get("PrivateIpAddress")
            if not private_ip:
                return {"status": "error", "message": "No private IP address"}

            # Test HTTP healthcheck endpoint
            url = f"http://{private_ip}/healthcheck"
            try:
                response = requests.get(url, timeout=5)
                if response.status_code == 200:
                    return {
                        "status": "healthy",
                        "http_code": response.status_code,
                        "response_time_ms": int(response.elapsed.total_seconds() * 1000),
                        "private_ip": private_ip,
                    }
                else:
                    return {
                        "status": "unhealthy",
                        "http_code": response.status_code,
                        "response_time_ms": int(response.elapsed.total_seconds() * 1000),
                        "private_ip": private_ip,
                        "message": f"HTTP {response.status_code}",
                    }
            except requests.exceptions.ConnectTimeout:
                return {"status": "timeout", "message": "Connection timeout", "private_ip": private_ip}
            except requests.exceptions.ConnectionError:
                return {"status": "connection_error", "message": "Connection refused", "private_ip": private_ip}
            except requests.exceptions.RequestException as e:
                return {"status": "error", "message": f"Request error: {str(e)}", "private_ip": private_ip}
        except Exception as e:
            return {"status": "error", "message": f"Unexpected error: {str(e)}"}

    def get_current_capacity(self) -> int:
        """Get the current capacity of the active ASG."""
        active_color = self.get_active_color()
        asg_name = self.get_asg_name(active_color)

        response = as_client.describe_auto_scaling_groups(AutoScalingGroupNames=[asg_name])

        if response["AutoScalingGroups"]:
            return response["AutoScalingGroups"][0]["DesiredCapacity"]
        return 0

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

        inactive_asg = self.get_asg_name(inactive_color)

        # Step 1: Scale up inactive ASG
        print(f"\nStep 1: Scaling up {inactive_asg} to {target_capacity} instances")
        self.scale_asg(inactive_asg, target_capacity)

        # Step 2: Wait for instances to be healthy in ASG
        print(f"\nStep 2: Waiting for instances in {inactive_asg} to be healthy")
        instances = self.wait_for_instances_healthy(inactive_asg)

        if len(instances) != target_capacity:
            raise RuntimeError(f"Expected {target_capacity} instances, but only {len(instances)} are healthy")

        # Step 3: Wait for instances to be healthy in target group
        print("\nStep 3: Waiting for instances to be healthy in target group")
        inactive_tg_arn = self.get_target_group_arn(inactive_color)
        self.wait_for_targets_healthy(inactive_tg_arn, instances)

        # Step 3.5: Optional HTTP health check (will timeout gracefully if security group not configured)
        if self.running_on_admin_node:
            print("\nStep 3.5: Checking HTTP health endpoints")
            try:
                self.wait_for_http_health(instances, timeout=30)  # Short timeout since this is optional
                print("HTTP health checks passed!")
            except TimeoutError:
                print("HTTP health checks timed out (this is normal if admin security group rule not applied)")
                print("Proceeding with deployment based on ALB target group health...")
        else:
            print("\nStep 3.5: Skipping HTTP health checks (not running on admin node)")
            print("Please manually verify instances are healthy before proceeding.")

        # Step 3.9: Additional confirmation when not on admin node
        if not self.running_on_admin_node and not skip_confirmation:
            print(f"\n⚠️  WARNING: About to switch traffic to {inactive_color} without HTTP health verification!")
            print("Since you're not running on the admin node, HTTP health checks were skipped.")
            print(f"Please ensure the {inactive_color} instances are responding properly before continuing.")

            response = input("\nDo you want to proceed with the traffic switch? (yes/no): ").strip().lower()
            if response not in ["yes", "y"]:
                print("Deployment cancelled. Traffic remains on current instances.")
                return

        # Step 4: Switch traffic to new color
        print(f"\nStep 4: Switching traffic to {inactive_color}")
        self.switch_target_group(inactive_color)

        print(f"\nBlue-green deployment complete! Now serving from {inactive_color}")
        print(f"Old {active_color} ASG remains running for rollback if needed")

    def rollback(self) -> None:
        """Rollback to the previous color."""
        current_color = self.get_active_color()
        previous_color = self.get_inactive_color()

        print(f"\nRolling back from {current_color} to {previous_color}")

        # Check if previous ASG has capacity
        previous_asg = self.get_asg_name(previous_color)
        response = as_client.describe_auto_scaling_groups(AutoScalingGroupNames=[previous_asg])

        if not response["AutoScalingGroups"]:
            raise ValueError(f"Previous ASG {previous_asg} not found")

        asg = response["AutoScalingGroups"][0]
        if asg["DesiredCapacity"] == 0:
            raise ValueError(f"Previous ASG {previous_asg} has no running instances for rollback")

        # Switch back
        self.switch_target_group(previous_color)
        print(f"Rollback complete! Now serving from {previous_color}")

    def cleanup_inactive(self) -> None:
        """Scale down the inactive ASG to save resources."""
        inactive_color = self.get_inactive_color()
        inactive_asg = self.get_asg_name(inactive_color)

        print(f"\nScaling down inactive {inactive_color} ASG")
        self.scale_asg(inactive_asg, 0)
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
            try:
                response = as_client.describe_auto_scaling_groups(AutoScalingGroupNames=[asg_name])
                if response["AutoScalingGroups"]:
                    asg = response["AutoScalingGroups"][0]
                    instance_ids = [i["InstanceId"] for i in asg["Instances"]]

                    # Get target group health
                    tg_healthy_count = 0
                    tg_status = "unknown"
                    if instance_ids:
                        try:
                            tg_arn = self.get_target_group_arn(color)
                            tg_health = elb_client.describe_target_health(
                                TargetGroupArn=tg_arn, Targets=[{"Id": iid} for iid in instance_ids]
                            )
                            healthy_count = 0
                            unused_count = 0

                            for target in tg_health["TargetHealthDescriptions"]:
                                state = target["TargetHealth"]["State"]
                                if state == "healthy":
                                    healthy_count += 1
                                elif state == "unused":
                                    unused_count += 1

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
                    http_health_results = {}
                    http_healthy_count = 0
                    http_skipped = False
                    if instance_ids:
                        for instance_id in instance_ids:
                            health_result = self.check_instance_health(instance_id)
                            http_health_results[instance_id] = health_result
                            if health_result["status"] == "healthy":
                                http_healthy_count += 1
                            elif health_result["status"] == "skipped":
                                http_skipped = True

                    status["asgs"][color] = {
                        "name": asg_name,
                        "desired": asg["DesiredCapacity"],
                        "min": asg["MinSize"],
                        "max": asg["MaxSize"],
                        "instances": len(asg["Instances"]),
                        "healthy_instances": len([i for i in asg["Instances"] if i["HealthStatus"] == "Healthy"]),
                        "target_group_healthy": tg_healthy_count,
                        "target_group_status": tg_status,
                        "http_health_results": http_health_results,
                        "http_healthy_count": http_healthy_count,
                        "http_skipped": http_skipped,
                    }
                else:
                    status["asgs"][color] = {"error": "ASG not found"}
            except ClientError as e:
                status["asgs"][color] = {"error": str(e)}

        return status
