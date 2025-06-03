"""Blue-green deployment CLI commands."""

from typing import Optional

import click

from lib.amazon import as_client, ec2_client, elb_client
from lib.aws_utils import get_asg_info, scale_asg
from lib.blue_green_deploy import BlueGreenDeployment, DeploymentCancelledException
from lib.ce_utils import are_you_sure
from lib.cli import cli
from lib.env import Config


@cli.group(name="blue-green")
def blue_green():
    """Blue-green deployment commands (BETA - for testing only)."""
    pass


@blue_green.command(name="status")
@click.option("--detailed", is_flag=True, help="Show detailed instance and target health information")
@click.pass_obj
def blue_green_status(cfg: Config, detailed: bool):
    """Show the current blue-green deployment status."""
    if cfg.env.value != "beta":
        print("Blue-green deployment is currently only available for beta environment")
        return

    deployment = BlueGreenDeployment(cfg)
    status = deployment.status()

    print(f"\nBlue-Green Status for {status['environment']}:")
    print(f"Active Color: {status['active_color']}")
    print(f"Inactive Color: {status['inactive_color']}")

    print("\nASG Status:")
    for color, asg_info in status["asgs"].items():
        if "error" in asg_info:
            print(f"  {color}: ERROR - {asg_info['error']}")
        else:
            active_marker = " (ACTIVE)" if color == status["active_color"] else ""
            print(f"  {color}{active_marker}:")
            print(f"    ASG Name: {asg_info['name']}")
            print(f"    Desired/Min/Max: {asg_info['desired']}/{asg_info['min']}/{asg_info['max']}")
            print(f"    ASG Health: {asg_info['healthy_instances']}/{asg_info['instances']} healthy")

            # Show target group health if available
            if "target_group_healthy" in asg_info:
                tg_status = asg_info["target_group_status"]
                tg_healthy = asg_info["target_group_healthy"]
                total_instances = asg_info["instances"]

                status_emoji = {
                    "all_healthy": "✅",
                    "all_unused": "🟡",  # Ready but not receiving traffic
                    "mixed_ready": "🔄",  # Some healthy, some unused
                    "partially_healthy": "⚠️",
                    "unhealthy": "❌",
                    "unknown": "❓",
                    "error": "💥",
                }.get(tg_status, "❓")

                print(f"    Target Group: {tg_healthy}/{total_instances} healthy {status_emoji}")

                if tg_status == "unhealthy" and total_instances > 0:
                    print("      Note: Instances may still be starting up or failing health checks")
                elif tg_status == "partially_healthy":
                    print("      Note: Some instances are still starting up")
                elif tg_status == "all_unused":
                    print("      Note: Instances are ready but not receiving traffic (standby)")
                elif tg_status == "mixed_ready":
                    print("      Note: Some instances receiving traffic, others on standby")
                elif tg_status == "error":
                    print("      Note: Error checking target group health")

            # Show HTTP health check results if available
            if "http_healthy_count" in asg_info:
                http_healthy = asg_info["http_healthy_count"]
                total_instances = asg_info["instances"]
                http_skipped = asg_info.get("http_skipped", False)

                if http_skipped:
                    print("    HTTP Health: skipped (not running on admin node) ℹ️")
                    if detailed:
                        print("      Note: Run from admin node to test HTTP endpoints directly")
                elif http_healthy == total_instances and total_instances > 0:
                    http_emoji = "✅"
                    print(f"    HTTP Health: {http_healthy}/{total_instances} healthy {http_emoji}")
                elif http_healthy > 0:
                    http_emoji = "⚠️"
                    print(f"    HTTP Health: {http_healthy}/{total_instances} healthy {http_emoji}")
                elif total_instances > 0:
                    http_emoji = "❌"
                    print(f"    HTTP Health: {http_healthy}/{total_instances} healthy {http_emoji}")
                else:
                    http_emoji = "⚪"  # No instances
                    print(f"    HTTP Health: {http_healthy}/{total_instances} healthy {http_emoji}")

            # Show detailed instance information if requested
            if detailed and asg_info.get("instances", 0) > 0:
                print("    Detailed Instance Status:")
                try:
                    deployment = BlueGreenDeployment(cfg)
                    asg_name = asg_info["name"]
                    response = as_client.describe_auto_scaling_groups(AutoScalingGroupNames=[asg_name])
                    if response["AutoScalingGroups"]:
                        asg = response["AutoScalingGroups"][0]

                        for instance in asg["Instances"]:
                            iid = instance["InstanceId"]
                            asg_health = instance["HealthStatus"]
                            lifecycle = instance["LifecycleState"]

                            # Get target group health for this instance
                            tg_health = "unknown"
                            try:
                                tg_arn = deployment.get_target_group_arn(color)
                                tg_response = elb_client.describe_target_health(
                                    TargetGroupArn=tg_arn, Targets=[{"Id": iid}]
                                )
                                if tg_response["TargetHealthDescriptions"]:
                                    tg_health = tg_response["TargetHealthDescriptions"][0]["TargetHealth"]["State"]
                            except Exception:
                                tg_health = "error"

                            # Get private IP address
                            private_ip = "unknown"
                            try:
                                ec2_response = ec2_client.describe_instances(InstanceIds=[iid])
                                if ec2_response["Reservations"] and ec2_response["Reservations"][0]["Instances"]:
                                    ec2_instance = ec2_response["Reservations"][0]["Instances"][0]
                                    private_ip = ec2_instance.get("PrivateIpAddress", "unknown")
                            except Exception:
                                private_ip = "error"

                            # Get HTTP health for this instance if available
                            http_health = "unknown"
                            http_details = ""
                            if "http_health_results" in asg_info and iid in asg_info["http_health_results"]:
                                http_result = asg_info["http_health_results"][iid]
                                http_health = http_result["status"]
                                if "response_time_ms" in http_result:
                                    http_details = f" ({http_result['response_time_ms']}ms)"
                                elif "message" in http_result:
                                    http_details = f" ({http_result['message']})"
                                # Use private_ip from HTTP health result if available (more reliable)
                                if "private_ip" in http_result:
                                    private_ip = http_result["private_ip"]

                            print(
                                f"      {iid}: IP={private_ip}, ASG={asg_health}, TG={tg_health}, HTTP={http_health}{http_details}, State={lifecycle}"
                            )

                except Exception as e:
                    print(f"      Error getting detailed status: {e}")


@blue_green.command(name="deploy")
@click.option("--capacity", type=int, help="Target capacity for deployment (default: match current)")
@click.option("--skip-confirmation", is_flag=True, help="Skip confirmation prompt")
@click.option("--branch", help="If version == 'latest', branch to get latest version from")
@click.argument("version", required=False)
@click.pass_obj
def blue_green_deploy(
    cfg: Config, capacity: int, skip_confirmation: bool, branch: Optional[str], version: Optional[str]
):
    """Deploy to the inactive color using blue-green strategy.

    Optionally specify VERSION to set before deployment.
    If VERSION is "latest" then the latest version (optionally filtered by --branch) is set.
    """
    if cfg.env.value != "beta":
        print("Blue-green deployment is currently only available for beta environment")
        return

    deployment = BlueGreenDeployment(cfg)

    active = deployment.get_active_color()
    inactive = deployment.get_inactive_color()

    # Show what version will be deployed if specified
    if version:
        print(f"\nWill set version to: {version}")

    if not skip_confirmation:
        confirm_msg = f"deploy to {inactive} (currently active: {active})"
        if version:
            confirm_msg += f" with version {version}"
        if not are_you_sure(confirm_msg, cfg):
            return

    try:
        deployment.deploy(target_capacity=capacity, skip_confirmation=skip_confirmation, version=version, branch=branch)
        print("\nDeployment successful!")
        print("Run 'ce blue-green rollback' if you need to revert")
    except DeploymentCancelledException:
        # Deployment was cancelled - don't show success message or raise
        return
    except Exception as e:
        print(f"\nDeployment failed: {e}")
        print("The inactive ASG may be partially scaled. Check status and clean up if needed.")
        raise


@blue_green.command(name="switch")
@click.argument("color", type=click.Choice(["blue", "green"]))
@click.option("--skip-confirmation", is_flag=True, help="Skip confirmation prompt")
@click.pass_obj
def blue_green_switch(cfg: Config, color: str, skip_confirmation: bool):
    """Manually switch to a specific color (blue or green)."""
    if cfg.env.value != "beta":
        print("Blue-green deployment is currently only available for beta environment")
        return

    deployment = BlueGreenDeployment(cfg)
    current = deployment.get_active_color()

    if current == color:
        print(f"Already serving from {color}")
        return

    if not skip_confirmation:
        if not are_you_sure(f"switch from {current} to {color}", cfg):
            return

    try:
        # Check if target ASG has capacity
        asg_name = deployment.get_asg_name(color)
        response = as_client.describe_auto_scaling_groups(AutoScalingGroupNames=[asg_name])

        if not response["AutoScalingGroups"] or response["AutoScalingGroups"][0]["DesiredCapacity"] == 0:
            print(f"Target ASG {asg_name} has no running instances")
            return

        deployment.switch_target_group(color)
        print(f"Successfully switched to {color}")
    except Exception as e:
        print(f"Switch failed: {e}")
        raise


@blue_green.command(name="rollback")
@click.option("--skip-confirmation", is_flag=True, help="Skip confirmation prompt")
@click.pass_obj
def blue_green_rollback(cfg: Config, skip_confirmation: bool):
    """Rollback to the previous color."""
    if cfg.env.value != "beta":
        print("Blue-green deployment is currently only available for beta environment")
        return

    deployment = BlueGreenDeployment(cfg)

    if not skip_confirmation:
        current = deployment.get_active_color()
        previous = deployment.get_inactive_color()
        if not are_you_sure(f"rollback from {current} to {previous}", cfg):
            return

    try:
        deployment.rollback()
    except Exception as e:
        print(f"Rollback failed: {e}")
        raise


@blue_green.command(name="cleanup")
@click.option("--skip-confirmation", is_flag=True, help="Skip confirmation prompt")
@click.pass_obj
def blue_green_cleanup(cfg: Config, skip_confirmation: bool):
    """Scale down the inactive ASG to save resources."""
    if cfg.env.value != "beta":
        print("Blue-green deployment is currently only available for beta environment")
        return

    deployment = BlueGreenDeployment(cfg)
    inactive = deployment.get_inactive_color()

    if not skip_confirmation:
        if not are_you_sure(f"scale down inactive {inactive} ASG", cfg):
            return

    try:
        deployment.cleanup_inactive()
    except Exception as e:
        print(f"Cleanup failed: {e}")
        raise


@blue_green.command(name="shutdown")
@click.option("--skip-confirmation", is_flag=True, help="Skip confirmation prompt")
@click.pass_obj
def blue_green_shutdown(cfg: Config, skip_confirmation: bool):
    """Shutdown the beta environment by scaling the active ASG to 0."""
    if cfg.env.value != "beta":
        print("Blue-green deployment is currently only available for beta environment")
        return

    deployment = BlueGreenDeployment(cfg)
    active_color = deployment.get_active_color()
    active_asg = deployment.get_asg_name(active_color)

    # Check if active ASG has any instances
    asg_info = get_asg_info(active_asg)
    if not asg_info or asg_info["DesiredCapacity"] == 0:
        print(f"Beta environment is already shut down (active {active_color} ASG has 0 instances)")
        return

    current_capacity = asg_info["DesiredCapacity"]

    if not skip_confirmation:
        print(f"⚠️  WARNING: This will shut down the beta environment by scaling the active {active_color} ASG to 0.")
        print(f"Currently serving traffic with {current_capacity} instance(s).")
        print("This will cause downtime until you deploy or switch to another color.")

        if not are_you_sure(f"shutdown beta environment (scale active {active_color} ASG to 0)", cfg):
            return

    try:
        print(f"Shutting down beta environment: scaling {active_asg} from {current_capacity} to 0 instances")
        scale_asg(active_asg, 0)
        print("✅ Beta environment shut down successfully")
        print("To restart: run 'ce --env beta blue-green deploy' or scale up manually")
    except Exception as e:
        print(f"Shutdown failed: {e}")
        raise


@blue_green.command(name="validate")
@click.pass_obj
def blue_green_validate(cfg: Config):
    """Validate the blue-green deployment setup."""
    if cfg.env.value != "beta":
        print("Blue-green deployment is currently only available for beta environment")
        return

    deployment = BlueGreenDeployment(cfg)

    print("Validating blue-green deployment setup...")

    issues = []

    # Check SSM parameters
    try:
        active_color = deployment.get_active_color()
        print(f"✓ Active color parameter exists: {active_color}")
    except Exception as e:
        issues.append(f"Cannot read active color parameter: {e}")

    # Check target groups
    for color in ["blue", "green"]:
        try:
            deployment.get_target_group_arn(color)
            print(f"✓ {color.capitalize()} target group exists")
        except Exception as e:
            issues.append(f"{color.capitalize()} target group not found: {e}")

    # Check ASGs
    for color in ["blue", "green"]:
        try:
            asg_name = deployment.get_asg_name(color)
            response = as_client.describe_auto_scaling_groups(AutoScalingGroupNames=[asg_name])
            if response["AutoScalingGroups"]:
                print(f"✓ {color.capitalize()} ASG exists: {asg_name}")
            else:
                issues.append(f"{color.capitalize()} ASG not found: {asg_name}")
        except Exception as e:
            issues.append(f"Error checking {color} ASG: {e}")

    # Check listener rule
    try:
        rule_arn = deployment.get_listener_rule_arn()
        if rule_arn:
            print("✓ ALB listener rule found")
        else:
            issues.append("ALB listener rule not found for /beta*")
    except Exception as e:
        issues.append(f"Error checking listener rule: {e}")

    if issues:
        print("\n❌ Validation failed with the following issues:")
        for issue in issues:
            print(f"  - {issue}")
    else:
        print("\n✅ All validation checks passed!")
