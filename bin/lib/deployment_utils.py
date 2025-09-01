"""General deployment utility functions for Compiler Explorer infrastructure."""

from __future__ import annotations

import time
from typing import Any

import requests
from botocore.exceptions import ClientError

from lib.amazon import as_client, elb_client
from lib.aws_utils import get_instance_private_ip
from lib.ce_utils import is_running_on_admin_node, print_elapsed_minutes, print_elapsed_time


def print_target_group_diagnostics(target_group_arn: str, instance_ids: list[str]) -> None:
    """Print diagnostic information about target group health status."""
    print("\nChecking target group status for diagnostic purposes...")
    try:
        response = elb_client.describe_target_health(
            TargetGroupArn=target_group_arn, Targets=[{"Id": iid} for iid in instance_ids]
        )
        print("Target group health status:")
        for target in response["TargetHealthDescriptions"]:
            state = target["TargetHealth"]["State"]
            reason = target["TargetHealth"].get("Reason", "")
            print(f"  {target['Target']['Id']}: {state} - {reason}")
    except Exception as e:
        print(f"  Could not check target group status: {e}")


def print_instance_details(instances: list[dict[str, Any]], prefix: str = "  ") -> None:
    """Print details for a list of instances."""
    for instance in instances:
        iid = instance["InstanceId"]
        health = instance["HealthStatus"]
        state = instance["LifecycleState"]
        print(f"{prefix}{iid}: ASG Health={health}, Lifecycle={state}")


def wait_for_instances_healthy(asg_name: str, timeout: int = 900) -> list[str]:
    """Wait for all instances in ASG to be InService (running).

    Note: This only waits for instances to be running, not for health checks to pass.
    Actual health verification is done by target group and HTTP health checks.
    """
    start_time = time.time()
    last_status_time = 0.0

    print(f"Waiting for instances in {asg_name} to be in service...")

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

            # For deployment, we only need instances to be InService (running)
            # The actual health checking is done by target group and HTTP checks
            all_instances = asg["Instances"]
            in_service_instances = [i["InstanceId"] for i in all_instances if i["LifecycleState"] == "InService"]

            current_time = time.time()

            if len(in_service_instances) == desired:
                print_elapsed_time("✅ All {count} instances in service", start_time, count=desired)

                # Print full status when all instances are in service
                print("Instance details:")
                print_instance_details(asg["Instances"])

                return in_service_instances

            # Only print status every 60 seconds to reduce noise
            if current_time - last_status_time >= 60:
                print_elapsed_minutes(
                    f"ASG {asg_name}: {len(in_service_instances)}/{desired} instances in service", start_time
                )

                # Debug output to diagnose status
                if len(in_service_instances) < desired:
                    print("  Instance states:")
                    print_instance_details(asg["Instances"], prefix="    ")

                last_status_time = current_time

        except ClientError as e:
            print(f"Error checking ASG health: {e}")

        time.sleep(30)  # Check every 30 seconds instead of 10

    raise TimeoutError(f"Timeout waiting for instances in {asg_name} to become healthy")


def wait_for_targets_healthy(target_group_arn: str, instance_ids: list[str], timeout: int = 600) -> list[str]:
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
                unhealthy.append({
                    "id": target["Target"]["Id"],
                    "state": target["TargetHealth"]["State"],
                    "reason": target["TargetHealth"].get("Reason", "Unknown"),
                })

        current_time = time.time()

        if len(healthy) == len(instance_ids):
            print_elapsed_time("✅ All {count} targets healthy", start_time, count=len(instance_ids))

            # Print full status when all targets are healthy
            print("Target health details:")
            for target in response["TargetHealthDescriptions"]:
                iid = target["Target"]["Id"]
                state = target["TargetHealth"]["State"]
                print(f"  {iid}: {state}")

            return healthy

        # Only print status every 30 seconds to reduce noise
        if current_time - last_status_time >= 30:
            print_elapsed_minutes(f"Target group health: {len(healthy)}/{len(instance_ids)} healthy", start_time)

            # Always show details when nothing is healthy yet
            if len(healthy) == 0 and unhealthy:
                print("  Target health details:")
                for u in unhealthy:
                    desc = f"{u['state']}"
                    if u.get("reason"):
                        desc += f" - {u['reason']}"
                    print(f"    {u['id']}: {desc}")
            # Only show detailed unhealthy info occasionally when some are healthy
            elif unhealthy and current_time - last_status_time >= 60:
                print(f"  Unhealthy targets: {[f'{u["id"]}: {u["state"]}' for u in unhealthy[:3]]}")
                if len(unhealthy) > 3:
                    print(f"  ... and {len(unhealthy) - 3} more")

            last_status_time = current_time

        time.sleep(15)  # Check every 15 seconds instead of 5

    raise TimeoutError("Timeout waiting for targets to become healthy")


def wait_for_http_health(instance_ids: list[str], timeout: int = 300) -> list[str]:
    """Wait for instances to respond healthy to HTTP health checks."""
    if not instance_ids:
        return []

    start_time = time.time()
    last_status_time = 0.0
    running_on_admin_node = is_running_on_admin_node()

    print(f"Testing HTTP health for {len(instance_ids)} instances...")

    while time.time() - start_time < timeout:
        healthy_instances = []
        unhealthy_instances = []

        for instance_id in instance_ids:
            health_result = check_instance_health(instance_id, running_on_admin_node)
            if health_result["status"] == "healthy":
                healthy_instances.append(instance_id)
            else:
                unhealthy_instances.append({
                    "id": instance_id,
                    "status": health_result["status"],
                    "message": health_result.get("message", "Unknown error"),
                })

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


def check_instance_health(instance_id: str, running_on_admin_node: bool) -> dict[str, Any]:
    """Check the health of an instance by testing its /healthcheck endpoint."""
    if not running_on_admin_node:
        return {
            "status": "skipped",
            "message": "HTTP health checks only available from admin node",
            "hostname": "local-machine",
        }

    try:
        # Get instance private IP
        private_ip = get_instance_private_ip(instance_id)
        if not private_ip:
            return {"status": "error", "message": "Instance not found or not running"}

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


def check_instance_compiler_registration(
    instance_id: str, environment: str, running_on_admin_node: bool
) -> dict[str, Any]:
    """Check if an instance has completed compiler registration by testing its /api/compilers endpoint."""
    if not running_on_admin_node:
        return {
            "status": "skipped",
            "message": "Compiler registration checks only available from admin node",
            "compiler_count": 0,
        }

    try:
        # Get instance private IP
        private_ip = get_instance_private_ip(instance_id)
        if not private_ip:
            return {"status": "error", "message": "Instance not found or not running", "compiler_count": 0}

        # Build API URL based on environment
        if environment == "prod":
            api_path = "/api/compilers"
        else:
            api_path = f"/{environment}/api/compilers"

        url = f"http://{private_ip}{api_path}?fields=id"

        try:
            response = requests.get(url, timeout=10, headers={"Accept": "application/json"})
            if response.status_code == 200:
                try:
                    compilers = response.json()
                    compiler_count = len(compilers) if isinstance(compilers, list) else 0

                    # Consider registration complete if we have at least some compilers
                    # This threshold can be adjusted based on expected minimum compiler count
                    # Exception: aarch64 environments are allowed to have 0 compilers
                    min_expected_compilers = 0 if environment.startswith("aarch64") else 5

                    if compiler_count >= min_expected_compilers:
                        return {
                            "status": "registered",
                            "compiler_count": compiler_count,
                            "private_ip": private_ip,
                            "response_time_ms": int(response.elapsed.total_seconds() * 1000),
                        }
                    else:
                        return {
                            "status": "partial",
                            "compiler_count": compiler_count,
                            "private_ip": private_ip,
                            "message": f"Only {compiler_count} compilers found (expected >={min_expected_compilers})",
                        }
                except ValueError:
                    return {
                        "status": "invalid_response",
                        "message": "Invalid JSON response from compilers API",
                        "private_ip": private_ip,
                        "compiler_count": 0,
                    }
            else:
                return {
                    "status": "api_error",
                    "http_code": response.status_code,
                    "private_ip": private_ip,
                    "message": f"Compilers API returned HTTP {response.status_code}",
                    "compiler_count": 0,
                }
        except requests.exceptions.ConnectTimeout:
            return {"status": "timeout", "message": "Connection timeout", "private_ip": private_ip, "compiler_count": 0}
        except requests.exceptions.ConnectionError:
            return {
                "status": "connection_error",
                "message": "Connection refused",
                "private_ip": private_ip,
                "compiler_count": 0,
            }
        except requests.exceptions.RequestException as e:
            return {
                "status": "error",
                "message": f"Request error: {str(e)}",
                "private_ip": private_ip,
                "compiler_count": 0,
            }
    except Exception as e:
        return {"status": "error", "message": f"Unexpected error: {str(e)}", "compiler_count": 0}


def wait_for_compiler_registration(instance_ids: list[str], environment: str, timeout: int = 600) -> list[str]:
    """Wait for instances to complete compiler registration and discovery."""
    if not instance_ids:
        return []

    start_time = time.time()
    last_status_time = 0.0
    running_on_admin_node = is_running_on_admin_node()

    print(f"Waiting for compiler registration on {len(instance_ids)} instances...")
    print("This ensures compilers are discovered and available before switching traffic.")

    if not running_on_admin_node:
        print("⚠️  Warning: Cannot verify compiler registration (not running on admin node)")
        print("   Waiting 30 seconds for compiler discovery to complete...")
        time.sleep(30)
        return instance_ids

    while time.time() - start_time < timeout:
        registered_instances = []
        pending_instances = []

        for instance_id in instance_ids:
            result = check_instance_compiler_registration(instance_id, environment, running_on_admin_node)
            if result["status"] == "registered":
                registered_instances.append(instance_id)
            else:
                pending_instances.append({
                    "id": instance_id,
                    "status": result["status"],
                    "compiler_count": result.get("compiler_count", 0),
                    "message": result.get("message", "Unknown"),
                })

        current_time = time.time()

        if len(registered_instances) == len(instance_ids):
            elapsed_secs = int(current_time - start_time)
            # Show total compiler count across all instances
            total_compilers = 0
            for instance_id in instance_ids:
                result = check_instance_compiler_registration(instance_id, environment, running_on_admin_node)
                total_compilers += result.get("compiler_count", 0)

            print(f"✅ All {len(instance_ids)} instances have completed compiler registration after {elapsed_secs}s")
            print(f"   Total compilers registered across all instances: {total_compilers}")
            return registered_instances

        # Show progress every 30 seconds
        if current_time - last_status_time >= 30:
            elapsed_secs = int(current_time - start_time)
            print(
                f"[{elapsed_secs}s] Compiler registration: {len(registered_instances)}/{len(instance_ids)} instances ready"
            )

            # Show details for pending instances
            if pending_instances:
                print("  Pending instances:")
                for pending in pending_instances[:3]:  # Show first 3 to avoid spam
                    print(f"    {pending['id']}: {pending['status']} ({pending['compiler_count']} compilers)")
                if len(pending_instances) > 3:
                    print(f"    ... and {len(pending_instances) - 3} more")

            last_status_time = current_time

        time.sleep(15)  # Check every 15 seconds

    raise TimeoutError(f"Timeout waiting for compiler registration on {len(instance_ids)} instances")
