"""Blue-green deployment CLI commands."""

from __future__ import annotations

import click
from botocore.exceptions import ClientError

from lib.amazon import (
    as_client,
    ec2_client,
    elb_client,
    get_current_key,
    get_releases,
    release_for,
)
from lib.aws_utils import get_asg_info, reset_asg_min_size, scale_asg
from lib.blue_green_deploy import BlueGreenDeployment, DeploymentCancelledException
from lib.builds_core import get_release_without_discovery_check
from lib.ce_utils import are_you_sure, display_releases
from lib.cli import cli
from lib.env import BLUE_GREEN_ENABLED_ENVIRONMENTS, Config, Environment
from lib.github_app import get_github_app_token
from lib.notify import handle_notify


def get_commit_hash_for_version(cfg: Config, version_key: str | None) -> str | None:
    """Convert a version key to its commit hash."""
    if not version_key:
        return None

    try:
        releases = get_releases(cfg)
        release = release_for(releases, version_key)
        return release.hash.hash if release else None
    except (ClientError, RuntimeError):
        return None


def get_commit_hash_for_version_param(cfg: Config, version: str | None, branch: str | None = None) -> str | None:
    """Convert a version parameter (from CLI) to its commit hash."""
    if not version:
        return None

    try:
        release = get_release_without_discovery_check(cfg, version, branch)
        return release.hash.hash if release else None
    except (ClientError, RuntimeError):
        return None


@cli.group(name="blue-green")
def blue_green():
    """Blue-green deployment commands."""
    pass


@blue_green.command(name="status")
@click.option("--detailed", is_flag=True, help="Show detailed instance and target health information")
@click.pass_obj
def blue_green_status(cfg: Config, detailed: bool):
    """Show the current blue-green deployment status."""
    if cfg.env.value not in BLUE_GREEN_ENABLED_ENVIRONMENTS:
        print(f"Blue-green deployment is only available for {', '.join(BLUE_GREEN_ENABLED_ENVIRONMENTS)} environments")
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
                            except ClientError:
                                tg_health = "error"

                            # Get private IP address
                            private_ip = "unknown"
                            try:
                                ec2_response = ec2_client.describe_instances(InstanceIds=[iid])
                                if ec2_response["Reservations"] and ec2_response["Reservations"][0]["Instances"]:
                                    ec2_instance = ec2_response["Reservations"][0]["Instances"][0]
                                    private_ip = ec2_instance.get("PrivateIpAddress", "unknown")
                            except ClientError:
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

                except ClientError as e:
                    print(f"      Error getting detailed status: {e}")


@blue_green.command(name="deploy")
@click.option("--capacity", type=int, help="Target capacity for deployment (default: match current)")
@click.option("--skip-confirmation", is_flag=True, help="Skip confirmation prompt")
@click.option("--branch", help="If version == 'latest', branch to get latest version from")
@click.option("--notify/--no-notify", help="Send GitHub notifications for newly released PRs (prod only)", default=None)
@click.option("--dry-run-notify", is_flag=True, help="Show what notifications would be sent without sending them")
@click.option("--check-notifications", is_flag=True, help="Only check what notifications would be sent, don't deploy")
@click.option(
    "--ignore-hash-mismatch", help="Continue deployment even if files have unexpected hash values", is_flag=True
)
@click.option("--skip-compiler-check", help="Skip compiler registration check before switching traffic", is_flag=True)
@click.option(
    "--compiler-timeout",
    type=int,
    default=600,
    help="Timeout in seconds for compiler registration check (default: 600)",
)
@click.argument("version", required=False)
@click.pass_obj
def blue_green_deploy(
    cfg: Config,
    capacity: int,
    skip_confirmation: bool,
    branch: str | None,
    notify: bool | None,
    dry_run_notify: bool,
    check_notifications: bool,
    ignore_hash_mismatch: bool,
    skip_compiler_check: bool,
    compiler_timeout: int,
    version: str | None,
):
    """Deploy to the inactive color using blue-green strategy.

    Optionally specify VERSION to set before deployment.
    If VERSION is "latest" then the latest version (optionally filtered by --branch) is set.
    If VERSION is "list" then available versions are listed instead of deploying.
    """
    if cfg.env.value not in BLUE_GREEN_ENABLED_ENVIRONMENTS:
        print(f"Blue-green deployment is only available for {', '.join(BLUE_GREEN_ENABLED_ENVIRONMENTS)} environments")
        return

    if version == "list":
        current = get_current_key(cfg) or ""
        releases = get_releases(cfg)
        branch_filter = set([branch]) if branch else set()
        display_releases(current, branch_filter, releases)
        return

    deployment = BlueGreenDeployment(cfg)

    active = deployment.get_active_color()
    inactive = deployment.get_inactive_color()

    # Track commit hashes for notifications (before deployment starts)
    original_commit_hash: str | None = None
    target_commit_hash: str | None = None

    if cfg.env == Environment.PROD:
        # Get original commit hash (what's currently deployed)
        original_version_key = get_current_key(cfg)
        original_commit_hash = get_commit_hash_for_version(cfg, original_version_key)

        # Get target commit hash (what we're deploying to)
        if version:
            target_commit_hash = get_commit_hash_for_version_param(cfg, version, branch)
        else:
            # No version specified means no change, use current
            target_commit_hash = original_commit_hash

    # Handle notification settings
    should_notify = notify
    if should_notify is None:
        # Default: notify on prod when there's actually a version change, don't notify on other environments
        should_notify = (
            cfg.env == Environment.PROD
            and original_commit_hash is not None
            and target_commit_hash is not None
            and original_commit_hash != target_commit_hash
        )

    # If dry-run-notify is specified, override to use dry-run mode
    if dry_run_notify:
        should_notify = True

    # Handle notification checking (if requested, show notifications and exit)
    if check_notifications:
        print(f"\n=== Notification Check for {cfg.env.value} ===")

        if cfg.env != Environment.PROD:
            print("❌ Notifications are only sent for production deployments")
            return

        if not version:
            print("❌ No version specified - no deployment would occur, no notifications sent")
            return

        print(f"Checking what notifications would be sent for deploying to version: {version}")

        if original_commit_hash and target_commit_hash:
            if original_commit_hash == target_commit_hash:
                print("❌ No version change detected - no notifications would be sent")
                print(f"   Current and target both point to: {original_commit_hash[:8]}...{original_commit_hash[-8:]}")
                return
            else:
                print("✅ Version change detected:")
                print(f"   From: {original_commit_hash[:8]}...{original_commit_hash[-8:]}")
                print(f"   To:   {target_commit_hash[:8]}...{target_commit_hash[-8:]}")
        else:
            print("❌ Could not determine commit hashes - notifications would be skipped")
            return

        print("✅ Will check commits between current deployment and target:")
        print(f"   From: {original_commit_hash[:8]}...{original_commit_hash[-8:]} (current deployment)")
        print(f"   To:   {target_commit_hash[:8]}...{target_commit_hash[-8:]} (target deployment)")

        # Show what would be notified
        print("\n🔍 Checking what would be notified...")
        gh_token = get_github_app_token()
        handle_notify(original_commit_hash, target_commit_hash, gh_token, dry_run=True)

        return

    # Show what version will be deployed if specified
    if version:
        print(f"\nWill set version to: {version}")

    if not skip_confirmation and not check_notifications:
        confirm_msg = f"deploy to {inactive} (currently active: {active})"
        if version:
            confirm_msg += f" with version {version}"
        if not are_you_sure(confirm_msg, cfg):
            return

    # Handle interactive confirmation for notifications if we're going to notify
    delay_notification_prompt = False
    if should_notify and cfg.env == Environment.PROD and not skip_confirmation and not dry_run_notify:
        notify_choice = click.prompt(
            "Send 'now live' notifications to GitHub issues/PRs?",
            type=click.Choice(["yes", "dry-run", "no", "delay"]),
            default="yes",
        )
        if notify_choice == "no":
            should_notify = False
        elif notify_choice == "dry-run":
            dry_run_notify = True
        elif notify_choice == "delay":
            delay_notification_prompt = True
            should_notify = False  # Don't notify immediately

    try:
        deployment.deploy(
            target_capacity=capacity,
            skip_confirmation=skip_confirmation,
            version=version,
            branch=branch,
            ignore_hash_mismatch=ignore_hash_mismatch,
            skip_compiler_check=skip_compiler_check,
            compiler_timeout=compiler_timeout,
        )
        print("\nDeployment successful!")
        print("Run 'ce blue-green rollback' if you need to revert")

        # Handle delayed notification prompt if requested
        if delay_notification_prompt and cfg.env == Environment.PROD:
            print("\n" + "=" * 60)
            delayed_notify_choice = click.prompt(
                "Deployment completed. Send 'now live' notifications to GitHub issues/PRs?",
                type=click.Choice(["yes", "dry-run", "no"]),
                default="yes",
            )
            if delayed_notify_choice in ["yes", "dry-run"]:
                should_notify = True
                dry_run_notify = delayed_notify_choice == "dry-run"

        # Send notifications after successful deployment (prod only)
        if should_notify and cfg.env == Environment.PROD:
            if original_commit_hash is not None and target_commit_hash is not None:
                try:
                    gh_token = get_github_app_token()
                    print(f"\n{'[DRY RUN] ' if dry_run_notify else ''}Checking for notifications...")
                    print(
                        f"Checking commits from {original_commit_hash[:8]}...{original_commit_hash[-8:]} to {target_commit_hash[:8]}...{target_commit_hash[-8:]}"
                    )
                    handle_notify(original_commit_hash, target_commit_hash, gh_token, dry_run=dry_run_notify)
                    print("Notification check completed.")
                except RuntimeError as e:
                    print(f"Warning: Failed to send notifications: {e}")
            else:
                if original_commit_hash is None:
                    print("No original commit hash available - skipping notifications.")
                if target_commit_hash is None:
                    print("No target commit hash available - skipping notifications.")

    except DeploymentCancelledException:
        # Deployment was cancelled - don't show success message or raise
        return
    except ClientError as e:
        print(f"\nDeployment failed: {e}")
        print("The inactive ASG may be partially scaled. Check status and clean up if needed.")
        raise


@blue_green.command(name="switch")
@click.argument("color", type=click.Choice(["blue", "green"]))
@click.option("--skip-confirmation", is_flag=True, help="Skip confirmation prompt")
@click.option("--force", is_flag=True, help="Force switch even if already serving from the requested color")
@click.pass_obj
def blue_green_switch(cfg: Config, color: str, skip_confirmation: bool, force: bool):
    """Manually switch to a specific color (blue or green)."""
    if cfg.env.value not in BLUE_GREEN_ENABLED_ENVIRONMENTS:
        print(f"Blue-green deployment is only available for {', '.join(BLUE_GREEN_ENABLED_ENVIRONMENTS)} environments")
        return

    deployment = BlueGreenDeployment(cfg)
    current = deployment.get_active_color()

    if current == color and not force:
        print(f"Already serving from {color}")
        return

    if current == color and force:
        print(f"Forcing switch to {color} (currently active color)")

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
    except ClientError as e:
        print(f"Switch failed: {e}")
        raise


@blue_green.command(name="rollback")
@click.option("--skip-confirmation", is_flag=True, help="Skip confirmation prompt")
@click.pass_obj
def blue_green_rollback(cfg: Config, skip_confirmation: bool):
    """Rollback to the previous color."""
    if cfg.env.value not in BLUE_GREEN_ENABLED_ENVIRONMENTS:
        print(f"Blue-green deployment is only available for {', '.join(BLUE_GREEN_ENABLED_ENVIRONMENTS)} environments")
        return

    deployment = BlueGreenDeployment(cfg)

    if not skip_confirmation:
        current = deployment.get_active_color()
        previous = deployment.get_inactive_color()
        if not are_you_sure(f"rollback from {current} to {previous}", cfg):
            return

    try:
        deployment.rollback()
    except ClientError as e:
        print(f"Rollback failed: {e}")
        raise


@blue_green.command(name="cleanup")
@click.option("--skip-confirmation", is_flag=True, help="Skip confirmation prompt")
@click.pass_obj
def blue_green_cleanup(cfg: Config, skip_confirmation: bool):
    """Scale down the inactive ASG to save resources."""
    if cfg.env.value not in BLUE_GREEN_ENABLED_ENVIRONMENTS:
        print(f"Blue-green deployment is only available for {', '.join(BLUE_GREEN_ENABLED_ENVIRONMENTS)} environments")
        return

    deployment = BlueGreenDeployment(cfg)
    inactive = deployment.get_inactive_color()

    if not skip_confirmation:
        if not are_you_sure(f"scale down inactive {inactive} ASG", cfg):
            return

    try:
        deployment.cleanup_inactive()
    except ClientError as e:
        print(f"Cleanup failed: {e}")
        raise


@blue_green.command(name="shutdown")
@click.option("--skip-confirmation", is_flag=True, help="Skip confirmation prompt")
@click.pass_obj
def blue_green_shutdown(cfg: Config, skip_confirmation: bool):
    """Shutdown the environment by scaling the active ASG to 0."""
    if cfg.env.value not in BLUE_GREEN_ENABLED_ENVIRONMENTS:
        print(f"Blue-green deployment is only available for {', '.join(BLUE_GREEN_ENABLED_ENVIRONMENTS)} environments")
        return

    deployment = BlueGreenDeployment(cfg)
    active_color = deployment.get_active_color()
    active_asg = deployment.get_asg_name(active_color)

    # Check if active ASG has any instances
    asg_info = get_asg_info(active_asg)
    if not asg_info or asg_info["DesiredCapacity"] == 0:
        print(
            f"{cfg.env.value.capitalize()} environment is already shut down (active {active_color} ASG has 0 instances)"
        )
        return

    current_capacity = asg_info["DesiredCapacity"]

    if not skip_confirmation:
        print(
            f"⚠️  WARNING: This will shut down the {cfg.env.value} environment by scaling the active {active_color} ASG to 0."
        )
        print(f"Currently serving traffic with {current_capacity} instance(s).")
        print("This will cause downtime until you deploy or switch to another color.")

        if not are_you_sure(f"shutdown {cfg.env.value} environment (scale active {active_color} ASG to 0)", cfg):
            return

    try:
        print(f"Shutting down {cfg.env.value} environment: scaling {active_asg} from {current_capacity} to 0 instances")
        # Need to set minimum size to 0 first, then scale down
        reset_asg_min_size(active_asg, 0)
        scale_asg(active_asg, 0)
        print(f"✅ {cfg.env.value.capitalize()} environment shut down successfully")
        print(f"To restart: run 'ce --env {cfg.env.value} blue-green deploy' or scale up manually")
    except ClientError as e:
        print(f"Shutdown failed: {e}")
        raise


@blue_green.command(name="validate")
@click.pass_obj
def blue_green_validate(cfg: Config):
    """Validate the blue-green deployment setup."""
    if cfg.env.value not in BLUE_GREEN_ENABLED_ENVIRONMENTS:
        print(f"Blue-green deployment is only available for {', '.join(BLUE_GREEN_ENABLED_ENVIRONMENTS)} environments")
        return

    deployment = BlueGreenDeployment(cfg)

    print("Validating blue-green deployment setup...")

    issues = []

    # Check SSM parameters
    try:
        active_color = deployment.get_active_color()
        print(f"✓ Active color parameter exists: {active_color}")
    except ClientError as e:
        issues.append(f"Cannot read active color parameter: {e}")

    # Check target groups
    for color in ["blue", "green"]:
        try:
            deployment.get_target_group_arn(color)
            print(f"✓ {color.capitalize()} target group exists")
        except ClientError as e:
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
        except ClientError as e:
            issues.append(f"Error checking {color} ASG: {e}")

    # Check listener rule
    try:
        rule_arn = deployment.get_listener_rule_arn()
        if rule_arn:
            if cfg.env.value == "prod":
                print("✓ ALB listener found for production")
            else:
                print("✓ ALB listener rule found")
        else:
            if cfg.env.value == "prod":
                issues.append("ALB listener not found for production")
            else:
                issues.append(f"ALB listener rule not found for /{cfg.env.value}*")
    except ClientError as e:
        issues.append(f"Error checking listener rule: {e}")

    if issues:
        print("\n❌ Validation failed with the following issues:")
        for issue in issues:
            print(f"  - {issue}")
    else:
        print("\n✅ All validation checks passed!")
