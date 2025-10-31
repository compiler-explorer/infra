#!/usr/bin/env python3

"""
CLI commands for CE Router killswitch - emergency routing control.
"""

from __future__ import annotations

import logging
import shlex
import time
from collections.abc import Sequence

import boto3
import click
from botocore.exceptions import ClientError

from lib.amazon import as_client, ec2
from lib.ce_utils import are_you_sure
from lib.cli import cli
from lib.env import Config
from lib.ssh import exec_remote, exec_remote_all

LOGGER = logging.getLogger(__name__)


@cli.group()
def ce_router():
    """CE Router emergency routing controls."""
    pass


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


def _enable_ce_router_rule(alb_client, env: str, rule_arn: str) -> bool:
    """Enable ce-router rule to route compilation traffic for specific environment."""
    try:
        # Set path patterns based on environment
        if env == "prod":
            path_patterns = ["/api/compiler/*/compile", "/api/compiler/*/cmake"]
        else:
            path_patterns = [f"/{env}/api/compiler/*/compile", f"/{env}/api/compiler/*/cmake"]

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

    # Show correct paths for the environment
    if environment == "prod":
        paths = "/api/compiler/*/compile, /api/compiler/*/cmake"
    else:
        paths = f"/{environment}/api/compiler/*/compile, /{environment}/api/compiler/*/cmake"

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
            click.echo(f"⚠️  CE Router routing for {env} is already enabled")
            continue

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
