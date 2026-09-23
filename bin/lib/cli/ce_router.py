#!/usr/bin/env python3

"""
CLI commands for CE Router: instance management and emergency routing control.

Both used to live in separate modules that each registered a click group named `ce-router`,
so whichever the loader imported second silently replaced the other.
"""

from __future__ import annotations

import json
import logging
import shlex
import sys
import time
from collections.abc import Sequence

import boto3
import click
from botocore.exceptions import ClientError

from lib import ce_router_smoke
from lib.amazon import as_client, ec2, ec2_client, elb_client
from lib.ce_utils import are_you_sure
from lib.cli import cli
from lib.compiler_routing import CompilerRoutingError, get_current_routing_table
from lib.env import Config
from lib.ssh import exec_remote, exec_remote_all, run_remote_shell

LOGGER = logging.getLogger(__name__)


@cli.group()
def ce_router():
    """CE Router instance management and emergency routing controls."""


class CERouterInstance:
    """Wrapper for CE Router instances to work with SSH utilities."""

    def __init__(self, instance):
        self.instance = instance
        self.elb_health = "unknown"
        self.service_status = {"SubState": "unknown"}
        self.running_version = "ce-router"

    def __str__(self):
        return f"{self.instance.id}@{self.instance.private_ip_address}"


def _get_ce_router_instances(cfg: Config) -> list[CERouterInstance]:
    """Get all CE Router instances from the ASG."""
    asg_name = f"ce-router-{cfg.env.name.lower()}"

    try:
        response = as_client.describe_auto_scaling_groups(AutoScalingGroupNames=[asg_name])

        if not response["AutoScalingGroups"]:
            LOGGER.warning(f"ASG '{asg_name}' not found")
            return []

        asg = response["AutoScalingGroups"][0]
        instance_ids = [instance["InstanceId"] for instance in asg["Instances"]]

        if not instance_ids:
            return []

        instances = []
        for instance_id in instance_ids:
            ec2_instance = ec2.Instance(id=instance_id)
            ec2_instance.load()
            instances.append(CERouterInstance(ec2_instance))

        return instances

    except ClientError as e:
        LOGGER.error(f"Error getting CE Router instances: {e}")
        return []


def _get_alb_client():
    """Get ALB (ELBv2) client."""
    return boto3.client("elbv2")


def _find_ce_router_target_groups(alb_client):
    """Find all ce-router target groups for different environments."""
    target_groups = {}
    environments = ["prod", "staging", "beta"]

    for env in environments:
        try:
            response = alb_client.describe_target_groups(Names=[f"ce-router-{env}"])
            if response["TargetGroups"]:
                target_groups[env] = {
                    "arn": response["TargetGroups"][0]["TargetGroupArn"],
                    "name": response["TargetGroups"][0]["TargetGroupName"],
                }
        except ClientError:
            # Target group doesn't exist for this environment
            pass

    return target_groups


def _find_compiler_explorer_listener(alb_client):
    """Find the HTTPS listener for the compiler-explorer ALB."""
    try:
        # Get all load balancers to find the compiler-explorer ALB
        response = alb_client.describe_load_balancers()

        compiler_explorer_lb = None
        for lb in response["LoadBalancers"]:
            lb_name = lb.get("LoadBalancerName", "")
            if "GccExplorerApp" in lb_name or "compiler-explorer" in lb_name.lower():
                compiler_explorer_lb = lb
                break

        if not compiler_explorer_lb:
            click.echo("Error: Could not find GccExplorerApp load balancer", err=True)
            return None

        # Get the HTTPS listener
        listeners_response = alb_client.describe_listeners(LoadBalancerArn=compiler_explorer_lb["LoadBalancerArn"])

        for listener in listeners_response["Listeners"]:
            if listener.get("Port") == 443:
                return listener["ListenerArn"]

        click.echo("Error: Could not find HTTPS listener", err=True)
        return None

    except ClientError as e:
        click.echo(f"Error finding HTTPS listener: {e}", err=True)
        return None


def _find_or_create_ce_router_rules(alb_client, listener_arn: str, target_groups: dict):
    """Find existing ce-router rules or create new ones for each environment."""
    rules = {}
    priority_base = 70  # Start at priority 70

    for env, tg_info in target_groups.items():
        target_group_arn = tg_info["arn"]

        try:
            # Get all rules for the HTTPS listener
            rules_response = alb_client.describe_rules(ListenerArn=listener_arn)

            # Look for existing ce-router rule for this environment
            ce_router_rule = None
            for rule in rules_response["Rules"]:
                if rule.get("Priority") == "default":
                    continue

                # Check if this rule forwards to this target group
                for action in rule.get("Actions", []):
                    if action.get("Type") == "forward" and action.get("TargetGroupArn") == target_group_arn:
                        ce_router_rule = rule
                        break

                if ce_router_rule:
                    break

            if ce_router_rule:
                rules[env] = ce_router_rule
                continue

            # No existing rule found, create a new one
            click.echo(f"🆕 Creating new ALB listener rule for ce-router-{env}...")

            # Use different priorities for each environment
            priority = priority_base + ["prod", "staging", "beta"].index(env)

            create_response = alb_client.create_rule(
                ListenerArn=listener_arn,
                Priority=priority,
                Conditions=[
                    {
                        "Field": "path-pattern",
                        "Values": [f"/killswitch-disabled-{env}-*"],  # Start disabled
                    }
                ],
                Actions=[{"Type": "forward", "TargetGroupArn": target_group_arn}],
            )

            rules[env] = create_response["Rules"][0]

        except ClientError as e:
            click.echo(f"Error finding/creating ce-router rule for {env}: {e}", err=True)
            continue

    return rules


def compilation_path_patterns(env: str) -> list[str]:
    """Path patterns for the compilation endpoints CE Router overrides."""
    prefix = "" if env == "prod" else f"/{env}"
    return [
        f"{prefix}/api/compiler/*/compile",
        f"{prefix}/api/compiler/*/cmake",
        f"{prefix}/api/compiler/*/build/*",
    ]


def get_rule_path_patterns(rule) -> list[str]:
    """Return the path patterns currently configured on a rule."""
    patterns = []
    for condition in rule.get("Conditions", []):
        if condition.get("Field") == "path-pattern":
            patterns.extend(condition.get("Values", []))
    return patterns


def _enable_ce_router_rule(alb_client, env: str, rule_arn: str) -> bool:
    """Enable ce-router rule to route compilation traffic for specific environment."""
    try:
        path_patterns = compilation_path_patterns(env)
        alb_client.modify_rule(RuleArn=rule_arn, Conditions=[{"Field": "path-pattern", "Values": path_patterns}])
        return True
    except ClientError as e:
        click.echo(f"Error enabling ce-router rule for {env}: {e}", err=True)
        return False


def _disable_ce_router_rule(alb_client, env: str, rule_arn: str) -> bool:
    """Disable ce-router rule by making conditions never match."""
    try:
        alb_client.modify_rule(
            RuleArn=rule_arn,
            Conditions=[
                {
                    "Field": "path-pattern",
                    "Values": [f"/killswitch-disabled-{env}-*"],  # Path that will never match
                }
            ],
        )
        return True
    except ClientError as e:
        click.echo(f"Error disabling ce-router rule for {env}: {e}", err=True)
        return False


def _get_ce_router_rule_status(rule) -> str:
    """Determine if ce-router rule is active based on its conditions."""
    if not rule:
        return "NOT_FOUND"

    for condition in rule.get("Conditions", []):
        if condition.get("Field") == "path-pattern":
            values = condition.get("Values", [])
            if "/killswitch-disabled-" in str(values):
                return "DISABLED"
            elif any("api/compiler" in v for v in values):
                return "ENABLED"

    return "UNKNOWN"


@ce_router.command("enable")
@click.option("--environment", "-e", required=True, help="Environment to enable (prod, staging, beta)")
@click.option("--skip-confirmation", is_flag=True, default=False, help="Skip confirmation prompt")
@click.pass_obj
def enable(cfg: Config, environment: str, skip_confirmation: bool):
    """
    Route compilation traffic to CE Router instances.

    This enables ALB routing to ce-router instances,
    bypassing Lambda or other routing for compilation requests.

    Examples:
        ce ce-router enable -e prod      # Enable for production
        ce ce-router enable -e staging   # Enable for staging
        ce ce-router enable -e beta      # Enable for beta
    """
    click.echo("🔧 CE ROUTER ROUTING CONTROL")
    click.echo("")

    paths = ", ".join(compilation_path_patterns(environment))

    click.echo(f"This will route {environment} compilation traffic to CE Router instances.")
    click.echo(f"Affected paths: {paths}")
    click.echo("")

    if not skip_confirmation and not click.confirm(f"Enable CE Router routing for {environment}?"):
        click.echo("Operation cancelled.")
        return

    alb_client = _get_alb_client()

    # Find ce-router target groups
    click.echo("🔍 Locating ce-router target groups...")
    target_groups = _find_ce_router_target_groups(alb_client)
    if not target_groups:
        click.echo("❌ Error: No ce-router target groups found", err=True)
        return

    # Filter by specified environment
    if environment not in target_groups:
        click.echo(f"❌ Error: ce-router-{environment} target group not found", err=True)
        return
    target_groups = {environment: target_groups[environment]}

    # Find HTTPS listener
    click.echo("🔍 Locating HTTPS listener...")
    listener_arn = _find_compiler_explorer_listener(alb_client)
    if not listener_arn:
        return

    # Find or create ce-router rules
    click.echo("🔍 Locating/creating ce-router ALB rules...")
    rules = _find_or_create_ce_router_rules(alb_client, listener_arn, target_groups)
    if not rules:
        return

    # Enable ce-router routing for each environment
    success_count = 0
    for env, rule in rules.items():
        rule_arn = rule["RuleArn"]
        current_status = _get_ce_router_rule_status(rule)

        if current_status == "ENABLED":
            if set(get_rule_path_patterns(rule)) == set(compilation_path_patterns(env)):
                click.echo(f"⚠️  CE Router routing for {env} is already enabled")
                continue
            click.echo(f"🔧 Updating ce-router ALB path patterns for {env}...")
        else:
            click.echo(f"🔧 Enabling ce-router ALB routing for {env}...")
        if _enable_ce_router_rule(alb_client, env, rule_arn):
            click.echo(f"✅ {env.upper()} ce-router routing enabled")
            success_count += 1
        else:
            click.echo(f"❌ Failed to enable ce-router routing for {env}", err=True)

    if success_count > 0:
        click.echo("")
        click.echo(f"✅ Compilation traffic for {success_count} environment(s) now routed to CE Router instances.")
    else:
        click.echo("")
        click.echo("❌ No environments were successfully enabled.", err=True)


@ce_router.command("disable")
@click.option("--environment", "-e", required=True, help="Environment to disable (prod, staging, beta)")
@click.option("--skip-confirmation", is_flag=True, default=False, help="Skip confirmation prompt")
@click.pass_obj
def disable(cfg: Config, environment: str, skip_confirmation: bool):
    """
    Disable CE Router routing, returning to default behavior.

    This disables the ce-router ALB rule, allowing traffic to fall back
    to whatever routing is configured as default (Lambda or instances).

    Examples:
        ce ce-router disable -e prod     # Disable for production
        ce ce-router disable -e staging  # Disable for staging
        ce ce-router disable -e beta     # Disable for beta
    """
    click.echo("🔧 CE ROUTER ROUTING CONTROL")
    click.echo("")
    click.echo(f"This will disable ce-router routing for {environment}.")
    click.echo("Traffic will fall back to default routing (Lambda or instances).")
    click.echo("")

    if not skip_confirmation and not click.confirm(f"Disable CE Router routing for {environment}?"):
        click.echo("Operation cancelled.")
        return

    alb_client = _get_alb_client()

    # Find ce-router target groups
    click.echo("🔍 Locating ce-router target groups...")
    target_groups = _find_ce_router_target_groups(alb_client)
    if not target_groups:
        click.echo("❌ Error: No ce-router target groups found", err=True)
        return

    # Filter by specified environment
    if environment not in target_groups:
        click.echo(f"❌ Error: ce-router-{environment} target group not found", err=True)
        return
    target_groups = {environment: target_groups[environment]}

    # Find HTTPS listener
    click.echo("🔍 Locating HTTPS listener...")
    listener_arn = _find_compiler_explorer_listener(alb_client)
    if not listener_arn:
        return

    # Find or create ce-router rules
    click.echo("🔍 Locating ce-router ALB rules...")
    rules = _find_or_create_ce_router_rules(alb_client, listener_arn, target_groups)
    if not rules:
        return

    # Disable ce-router routing for each environment
    success_count = 0
    for env, rule in rules.items():
        rule_arn = rule["RuleArn"]
        current_status = _get_ce_router_rule_status(rule)

        if current_status == "DISABLED":
            click.echo(f"⚠️  CE Router routing for {env} is already disabled")
            continue

        click.echo(f"🔧 Disabling ce-router ALB routing for {env}...")
        if _disable_ce_router_rule(alb_client, env, rule_arn):
            click.echo(f"✅ {env.upper()} ce-router routing disabled")
            success_count += 1
        else:
            click.echo(f"❌ Failed to disable ce-router routing for {env}", err=True)

    if success_count > 0:
        click.echo("")
        click.echo(
            f"✅ CE Router routing disabled for {success_count} environment(s). Traffic returned to default routing."
        )
    else:
        click.echo("")
        click.echo("❌ No environments were successfully disabled.", err=True)


@ce_router.command("status")
@click.pass_obj
def status(cfg: Config):
    """
    Show the current status of CE Router ALB routing.

    This checks the actual ALB listener rules, not Terraform configuration.

    Example:
        ce ce-router status
    """
    click.echo("📊 CE Router ALB Routing Status")
    click.echo("=" * 35)

    alb_client = _get_alb_client()

    try:
        # Find ce-router target groups
        target_groups = _find_ce_router_target_groups(alb_client)
        if not target_groups:
            click.echo("CE-ROUTER | 🔴 NOT_CONFIGURED (no target groups found)")
            return

        # Find HTTPS listener
        listener_arn = _find_compiler_explorer_listener(alb_client)
        if not listener_arn:
            click.echo("CE-ROUTER | 🔴 ERROR (HTTPS listener not found)")
            return

        # Find ce-router rules
        rules = _find_or_create_ce_router_rules(alb_client, listener_arn, target_groups)
        if not rules:
            click.echo("CE-ROUTER | 🔴 ERROR (could not find/create rules)")
            return

        # Show status for each environment
        for env, rule in rules.items():
            target_group_arn = target_groups[env]["arn"]
            rule_status = _get_ce_router_rule_status(rule)
            rule_arn_short = rule["RuleArn"].split("/")[-1]
            rule_priority = rule.get("Priority", "unknown")

            if rule_status == "ENABLED":
                status_text = "🟢 ACTIVE (routing compilation traffic)"
            elif rule_status == "DISABLED":
                status_text = "🔴 DISABLED (using default routing)"
            else:
                status_text = f"🟡 {rule_status}"

            rule_info = f"Rule: {rule_arn_short} (Priority: {rule_priority})"

            click.echo(f"{env.upper():<8} | {status_text}")
            click.echo(f"         | {rule_info}")

            # Also check target group health
            try:
                health_response = alb_client.describe_target_health(TargetGroupArn=target_group_arn)
                healthy_targets = sum(
                    1 for t in health_response["TargetHealthDescriptions"] if t["TargetHealth"]["State"] == "healthy"
                )
                total_targets = len(health_response["TargetHealthDescriptions"])

                click.echo(f"         | Healthy targets: {healthy_targets}/{total_targets}")

            except ClientError as e:
                click.echo(f"         | Target health: Error ({e})")

            click.echo("")  # Add spacing between environments

    except ClientError as e:
        click.echo(f"CE-ROUTER | ❌ ERROR: {str(e)}")


@ce_router.command(name="exec_all")
@click.pass_obj
@click.argument("remote_cmd", required=True, nargs=-1)
def exec_all(cfg: Config, remote_cmd: Sequence[str]):
    """
    Execute REMOTE_CMD on all CE Router instances.

    Examples:
        ce ce-router exec_all uptime
        ce ce-router exec_all sudo systemctl status ce-router
        ce ce-router exec_all curl -f http://localhost:10240/healthcheck
    """
    instances = _get_ce_router_instances(cfg)

    if not instances:
        click.echo(f"No CE Router instances found for environment {cfg.env.name}")
        return

    escaped = shlex.join(remote_cmd)
    if not are_you_sure(f"exec command {escaped} on all {len(instances)} CE Router instances", cfg):
        return

    click.echo(f"Running '{escaped}' on {len(instances)} CE Router instances...")
    exec_remote_all(instances, remote_cmd)


@ce_router.command(name="version")
@click.pass_obj
def version(cfg: Config):
    """
    Show the installed CE Router version on all instances.

    Example:
        ce ce-router version
    """
    instances = _get_ce_router_instances(cfg)

    if not instances:
        click.echo(f"No CE Router instances found for environment {cfg.env.name}")
        return

    click.echo(f"CE Router versions for {cfg.env.name}:")
    click.echo("")

    for instance in instances:
        try:
            version_output = exec_remote(instance, ["cat", "/infra/.deploy/ce-router-version"], ignore_errors=True)
            version_str = version_output.strip() if version_output else "unknown"
            click.echo(f"  {instance}: {version_str}")
        except RuntimeError:
            click.echo(f"  {instance}: error reading version")


@ce_router.command(name="refresh")
@click.option(
    "--min-healthy-percent",
    type=click.IntRange(min=0, max=100),
    metavar="PERCENT",
    help="While updating, ensure at least PERCENT are healthy",
    default=75,
    show_default=True,
)
@click.option("--skip-confirmation", is_flag=True, help="Skip confirmation prompt")
@click.pass_obj
def refresh(cfg: Config, min_healthy_percent: int, skip_confirmation: bool):
    """
    Refresh CE Router instances by replacing them with new ones.

    This starts an AWS instance refresh which will:
    1. Launch new instances with the latest CE Router version
    2. Wait for them to become healthy
    3. Terminate old instances
    4. Repeat until all instances are replaced

    The refresh maintains the specified minimum healthy percentage throughout.

    Example:
        ce ce-router refresh
        ce ce-router refresh --min-healthy-percent 90
    """
    asg_name = f"ce-router-{cfg.env.name.lower()}"

    try:
        # Check if ASG exists
        response = as_client.describe_auto_scaling_groups(AutoScalingGroupNames=[asg_name])

        if not response["AutoScalingGroups"]:
            click.echo(f"ASG '{asg_name}' not found")
            return

        asg = response["AutoScalingGroups"][0]

        if asg["DesiredCapacity"] == 0:
            click.echo(f"Skipping ASG {asg_name} as it has zero desired capacity")
            return

        # Check for existing refresh
        describe_state = as_client.describe_instance_refreshes(AutoScalingGroupName=asg_name)
        existing_refreshes = [
            x for x in describe_state["InstanceRefreshes"] if x["Status"] in ("Pending", "InProgress")
        ]

        if existing_refreshes:
            refresh_id = existing_refreshes[0]["InstanceRefreshId"]
            click.echo(f"Found existing refresh {refresh_id} for {asg_name}")
        else:
            if not skip_confirmation and not are_you_sure(
                f"refresh CE Router instances in {asg_name} (min healthy: {min_healthy_percent}%)", cfg
            ):
                return

            click.echo("Starting instance refresh...")
            refresh_result = as_client.start_instance_refresh(
                AutoScalingGroupName=asg_name, Preferences={"MinHealthyPercentage": min_healthy_percent}
            )
            refresh_id = refresh_result["InstanceRefreshId"]
            click.echo(f"Refresh started with ID: {refresh_id}")

        # Monitor progress
        last_log = ""
        while True:
            time.sleep(5)
            describe_state = as_client.describe_instance_refreshes(
                AutoScalingGroupName=asg_name, InstanceRefreshIds=[refresh_id]
            )
            refresh_data = describe_state["InstanceRefreshes"][0]
            status = refresh_data["Status"]

            if status == "InProgress":
                log = (
                    f"  {status}, {refresh_data['PercentageComplete']}%, "
                    f"{refresh_data['InstancesToUpdate']} to update. "
                    f"{refresh_data.get('StatusReason', '')}"
                )
            else:
                log = f"  Status: {status}"

            if log != last_log:
                click.echo(log)
                last_log = log

            if status in ("Successful", "Failed", "Cancelled"):
                break

        if status == "Successful":
            click.echo("")
            click.echo("Instance refresh completed successfully!")
            click.echo("New instances are now running with the latest CE Router version.")
        elif status == "Failed":
            click.echo("")
            click.echo(f"Instance refresh failed: {refresh_data.get('StatusReason', 'Unknown reason')}")
        else:
            click.echo("")
            click.echo("Instance refresh was cancelled")

    except ClientError as e:
        click.echo(f"Error refreshing CE Router instances: {e}")


@ce_router.command(name="instances")
@click.pass_obj
def ce_router_instances(cfg: Config) -> None:
    """Show CE Router ASG capacity and per-instance health."""
    asg_name = f"ce-router-{cfg.env.name.lower()}"

    try:
        # Get ASG information
        response = as_client.describe_auto_scaling_groups(AutoScalingGroupNames=[asg_name])

        if not response["AutoScalingGroups"]:
            print(f"ASG '{asg_name}' not found")
            return

        asg = response["AutoScalingGroups"][0]

        print("CE Router ASG Status:")
        print(f"  Name: {asg['AutoScalingGroupName']}")
        print(f"  Min Size: {asg['MinSize']}")
        print(f"  Desired Capacity: {asg['DesiredCapacity']}")
        print(f"  Max Size: {asg['MaxSize']}")
        print(f"  Instances: {len(asg['Instances'])}")

        # Show instance details
        if asg["Instances"]:
            print("\n  Instance Details:")
            instance_ids = [instance["InstanceId"] for instance in asg["Instances"]]

            # Get instance information from EC2
            ec2_response = ec2_client.describe_instances(InstanceIds=instance_ids)

            for reservation in ec2_response["Reservations"]:
                for instance in reservation["Instances"]:
                    instance_id = instance["InstanceId"]
                    state = instance["State"]["Name"]
                    launch_time = instance.get("LaunchTime", "Unknown")
                    private_ip = instance.get("PrivateIpAddress", "N/A")

                    # Find corresponding ASG instance for lifecycle state
                    asg_instance: dict = next((i for i in asg["Instances"] if i["InstanceId"] == instance_id), {})
                    lifecycle_state = asg_instance.get("LifecycleState", "Unknown")

                    print(f"    {instance_id}: {state} ({lifecycle_state}) - {private_ip} - {launch_time}")

        # Check target group health
        try:
            target_groups = elb_client.describe_target_groups(Names=[f"ce-router-{cfg.env.name.lower()}"])

            if target_groups["TargetGroups"]:
                tg_arn = target_groups["TargetGroups"][0]["TargetGroupArn"]
                health_response = elb_client.describe_target_health(TargetGroupArn=tg_arn)

                print("\n  Target Group Health:")
                for target in health_response["TargetHealthDescriptions"]:
                    target_id = target["Target"]["Id"]
                    health_state = target["TargetHealth"]["State"]
                    print(f"    {target_id}: {health_state}")

        except ClientError as e:
            print(f"  Could not retrieve target group health: {e}")

    except ClientError as e:
        print(f"Error retrieving CE Router status: {e}")


def _healthy_router_count(cfg: Config) -> int | None:
    """Instances the ALB is willing to send requests to, or None if the group cannot be read."""
    try:
        groups = elb_client.describe_target_groups(Names=[f"ce-router-{cfg.env.name.lower()}"])
        if not groups["TargetGroups"]:
            return None
        health = elb_client.describe_target_health(TargetGroupArn=groups["TargetGroups"][0]["TargetGroupArn"])
        return sum(1 for t in health["TargetHealthDescriptions"] if t["TargetHealth"]["State"] == "healthy")
    except ClientError:
        return None


def _wait_for_router_capacity(cfg: Config, asg_name: str, desired: int, timeout_seconds: int = 600) -> int:
    """Block until the target group reports `desired` healthy routers, and report what it saw.

    Asking the ASG alone is not enough: an instance counts as InService well before the ALB
    health check passes, so a scale that only waited on the ASG would hand back a fleet that is
    not yet taking traffic - and a test run against it would be measuring the old capacity.
    """
    deadline = time.time() + timeout_seconds
    healthy = 0
    last_report = ""
    while time.time() < deadline:
        asg = as_client.describe_auto_scaling_groups(AutoScalingGroupNames=[asg_name])["AutoScalingGroups"][0]
        in_service = sum(1 for i in asg["Instances"] if i["LifecycleState"] == "InService")
        counted = _healthy_router_count(cfg)
        if counted is None:
            # No target group to consult (the routing may not be enabled); InService is all there is.
            return in_service if in_service >= desired else in_service
        healthy = counted
        report = f"  {len(asg['Instances'])} in ASG, {in_service} InService, {healthy} healthy in target group"
        if report != last_report:
            print(report)
            last_report = report
        if healthy >= desired and in_service >= desired:
            return healthy
        time.sleep(10)
    return healthy


@ce_router.command(name="scale")
@click.argument("desired_capacity", type=int, required=True)
@click.option("--skip-confirmation", is_flag=True, help="Skip confirmation prompt")
@click.pass_obj
def ce_router_scale(cfg: Config, desired_capacity: int, skip_confirmation: bool) -> None:
    """Manually scale CE Router instances to DESIRED_CAPACITY."""
    asg_name = f"ce-router-{cfg.env.name.lower()}"

    if not skip_confirmation and not are_you_sure(f"scale CE Router ASG to {desired_capacity} instances", cfg):
        return

    try:
        current = as_client.describe_auto_scaling_groups(AutoScalingGroupNames=[asg_name])["AutoScalingGroups"][0]

        # DesiredCapacity outside [MinSize, MaxSize] is rejected, so move the bounds with it.
        update: dict = {"AutoScalingGroupName": asg_name, "DesiredCapacity": desired_capacity}
        if desired_capacity > current["MaxSize"]:
            update["MaxSize"] = desired_capacity
            print(f"Raising MaxSize from {current['MaxSize']} to {desired_capacity}")
        if desired_capacity < current["MinSize"]:
            update["MinSize"] = desired_capacity
            print(f"Lowering MinSize from {current['MinSize']} to {desired_capacity}")

        print(f"Scaling CE Router ASG from {current['DesiredCapacity']} to {desired_capacity} instances...")
        as_client.update_auto_scaling_group(**update)

        healthy = _wait_for_router_capacity(cfg, asg_name, desired_capacity)
        if healthy == desired_capacity:
            print(f"CE Router ASG is serving traffic from {healthy} instance(s)")
        else:
            print(
                f"Gave up waiting: {healthy} of {desired_capacity} instance(s) are healthy in the target group. "
                f"Run 'ce --env {cfg.env.name.lower()} ce-router instances' to see where they are stuck.",
                file=sys.stderr,
            )
            raise SystemExit(1)

    except ClientError as e:
        print(f"Error scaling CE Router ASG: {e}")
        raise SystemExit(1) from e


@ce_router.command(name="login")
@click.option("--instance-id", help="Specific instance ID to login to")
@click.pass_obj
def ce_router_login(cfg: Config, instance_id: str | None) -> None:
    """SSH into a CE Router instance."""
    asg_name = f"ce-router-{cfg.env.name.lower()}"

    try:
        # Get instances from ASG
        response = as_client.describe_auto_scaling_groups(AutoScalingGroupNames=[asg_name])

        if not response["AutoScalingGroups"]:
            print(f"ASG '{asg_name}' not found")
            return

        asg = response["AutoScalingGroups"][0]
        instance_ids = [instance["InstanceId"] for instance in asg["Instances"]]

        if not instance_ids:
            print("No instances found in CE Router ASG")
            return

        # Select instance to login to
        if instance_id:
            if instance_id not in instance_ids:
                print(f"Instance {instance_id} not found in CE Router ASG")
                return
            target_instance_id = instance_id
        else:
            # Use first available instance
            target_instance_id = instance_ids[0]
            print(f"Logging into instance {target_instance_id} (first available)")

        # Get instance details
        ec2_response = ec2_client.describe_instances(InstanceIds=[target_instance_id])
        instance = ec2_response["Reservations"][0]["Instances"][0]

        print(f"Connecting to CE Router instance {target_instance_id}...")
        run_remote_shell(instance)

    except ClientError as e:
        print(f"Error logging into CE Router instance: {e}")


@ce_router.command(name="restart")
@click.option("--skip-confirmation", is_flag=True, help="Skip confirmation prompt")
@click.pass_obj
def ce_router_restart(cfg: Config, skip_confirmation: bool) -> None:
    """Restart CE Router service on all instances."""
    asg_name = f"ce-router-{cfg.env.name.lower()}"

    if not skip_confirmation and not are_you_sure("restart CE Router service on all instances", cfg):
        return

    try:
        # Get instances from ASG
        response = as_client.describe_auto_scaling_groups(AutoScalingGroupNames=[asg_name])

        if not response["AutoScalingGroups"]:
            print(f"ASG '{asg_name}' not found")
            return

        asg = response["AutoScalingGroups"][0]
        instance_ids = [instance["InstanceId"] for instance in asg["Instances"]]

        if not instance_ids:
            print("No instances found in CE Router ASG")
            return

        print(f"Restarting CE Router service on {len(instance_ids)} instances...")
        exec_remote_all(instance_ids, ["sudo", "systemctl", "restart", "ce-router"])

        # Wait a moment for services to start
        time.sleep(5)

        print("Checking service status...")
        exec_remote_all(instance_ids, ["sudo", "systemctl", "status", "ce-router", "--no-pager"])

    except ClientError as e:
        print(f"Error restarting CE Router service: {e}")


def format_healthcheck(response: str) -> str:
    """Summarise the JSON a router's /healthcheck returns."""
    try:
        payload = json.loads(response)
    except json.JSONDecodeError:
        body = response.strip()[:100] or "(empty)"
        return f"❌ UNHEALTHY - unparseable response: {body}"

    if payload.get("status") != "healthy":
        return f"❌ UNHEALTHY - {payload.get('reason', 'no reason given')}"

    # The router only fails its healthcheck once reconnection attempts are exhausted, so a
    # disconnected socket still answers 200 while routing nothing.
    if payload.get("websocket") != "connected":
        return f"⚠️  HEALTHY but websocket is {payload.get('websocket', 'unknown')}"

    return "✅ HEALTHY"


@ce_router.command(name="healthcheck")
@click.pass_obj
def ce_router_healthcheck(cfg: Config) -> None:
    """Send healthcheck requests to all CE Router instance private IPs."""
    instances = _get_ce_router_instances(cfg)

    if not instances:
        click.echo(f"No CE Router instances found for environment {cfg.env.name}")
        return

    click.echo(f"Checking health of {len(instances)} CE Router instances...")

    for instance in instances:
        state = instance.instance.state["Name"]
        if state != "running":
            click.echo(f"  {instance}: SKIPPED - instance state is {state}")
            continue

        url = f"http://{instance.instance.private_ip_address}/healthcheck"
        try:
            # Deliberately no -f: an unhealthy router answers 503 with a body saying why,
            # and that body is the point of asking.
            response = exec_remote(instance, ["curl", "-s", url])
        except RuntimeError as e:
            click.echo(f"  {instance}: ❌ ERROR - {e}")
            continue

        click.echo(f"  {instance}: {format_healthcheck(response)}")


@ce_router.command(name="smoke")
@click.option("--compiler", help="Queue-routed compiler to exercise (default: picked from the routing table)")
@click.option("--url-compiler", help="URL-routed compiler to exercise (default: picked from the routing table)")
@click.option("--unrouted-compiler", help="Compiler deliberately absent from the routing table")
@click.option("--url", "base_override", help="API root to hit, e.g. https://alb.godbolt.org to bypass CloudFront")
@click.option(
    "--build-system",
    "build_systems",
    multiple=True,
    default=("cmake", "cargo", "make"),
    show_default=True,
    help="Build systems to exercise; each uses its own manifest and language",
)
@click.option("--iterations", default=50, show_default=True, help="Repeats for the cache-hit loop")
@click.option(
    "--concurrency",
    default=20,
    show_default=True,
    help="Requests to put in flight at once; the check that more than one router can be tested by",
)
@click.option("--skip-slow", is_flag=True, help="Skip the oversized request/response and boundary-sweep checks")
@click.option("--ignore-known", is_flag=True, help="Exit 0 even if checks tracked by an open issue fail")
@click.pass_obj
def smoke(
    cfg: Config,
    compiler: str | None,
    url_compiler: str | None,
    unrouted_compiler: str | None,
    base_override: str | None,
    build_systems: Sequence[str],
    iterations: int,
    concurrency: int,
    skip_slow: bool,
    ignore_known: bool,
):
    """
    Run the functional checks from docs/ce-router-cutover-checklist.md section C.

    Exercises each distinct path through the router - queue routing, URL routing, the S3
    overflow path for oversized requests and the s3Key path for oversized results - and
    asserts on what the caller actually receives, since several of these failures return
    HTTP 200 with a broken body.

    Example:
        ce --env beta ce-router smoke
        ce --env beta ce-router smoke --compiler g132 --skip-slow
    """
    environment = cfg.env.value
    base = ce_router_smoke.base_url(environment, base_override)

    workers = ce_router_smoke.in_service_worker_count(environment)
    if workers == 0:
        click.echo(f"No in-service workers in {environment} - every check would wait out the 60s router", err=True)
        click.echo("deadline and report a failure that says nothing about the router. Bring the", err=True)
        click.echo(f"environment up first:  ce --env {environment} environment start", err=True)
        raise SystemExit(2)
    if workers is not None:
        click.echo(f"Workers     : {workers} in service")

    cpp_ids = ce_router_smoke.cpp_compiler_ids(base)
    if not compiler:
        compiler = ce_router_smoke.pick_cpp_compiler(base, candidates=cpp_ids)
    if not url_compiler:
        click.echo("Reading the routing table for a URL-routed C++ compiler...")
        try:
            table = get_current_routing_table(environment)
        except CompilerRoutingError as e:
            click.echo(f"Could not read the routing table: {e}", err=True)
            table = {}
        candidates = []
        for key, entry in sorted(table.items()):
            compiler_id = key.split("#", 1)[-1]
            # Language matters: a URL-routed Go compiler cannot build the C++ these checks send.
            if entry.get("routingType") == "url" and (not cpp_ids or compiler_id in cpp_ids):
                candidates.append(compiler_id)
        url_compiler = ce_router_smoke.first_compiler_that_works(base, candidates)
        if candidates and not url_compiler:
            click.echo(f"None of the first URL-routed candidates compiled the fixture: {', '.join(candidates[:8])}")

    if not compiler:
        click.echo("No queue-routed compiler found or given; pass --compiler", err=True)
        raise SystemExit(2)

    click.echo(f"Environment : {environment}")
    click.echo(f"API root    : {base}")
    click.echo(f"Queue-routed: {compiler}")
    click.echo(f"URL-routed  : {url_compiler or '(none - skipping that check)'}")
    click.echo("")

    findings = ce_router_smoke.run_checks(
        base=base,
        queue_compiler=compiler,
        url_compiler=url_compiler,
        unrouted_compiler=unrouted_compiler,
        build_systems=tuple(build_systems),
        loop_iterations=iterations,
        concurrency=concurrency,
        skip_slow=skip_slow,
    )

    click.echo("")
    for result in findings.results:
        if result.ok:
            mark = "FIXED" if result.tracked else "PASS"
        else:
            mark = "KNOWN" if result.tracked else "FAIL"
        timing = f"{result.seconds:6.2f}s" if result.seconds else "       "
        suffix = f"  [{result.tracked}]" if result.tracked else ""
        click.echo(f"  [{mark:5}] {timing}  {result.name}: {result.detail}{suffix}")

    click.echo("")
    passed = len([r for r in findings.results if r.ok])
    click.echo(f"{passed}/{len(findings.results)} passed.")
    if findings.known:
        click.echo(f"{len(findings.known)} failing against an open issue:")
        for result in findings.known:
            click.echo(f"    {result.tracked}: {result.name}")
    if findings.unexpectedly_fixed:
        click.echo("Tracked checks passing here - either the fix landed, or this path is not exercised:")
        for result in findings.unexpectedly_fixed:
            click.echo(f"    {result.tracked}: {result.name}")

    if findings.failed:
        click.echo(f"\n{len(findings.failed)} untracked failure(s).", err=True)
        raise SystemExit(1)
    if findings.known and not ignore_known:
        click.echo("\nOnly tracked issues failed; pass --ignore-known to exit 0.", err=True)
        raise SystemExit(1)
