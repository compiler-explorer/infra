#!/usr/bin/env python3

"""
CLI commands for CE Router killswitch - emergency routing control.
"""

from __future__ import annotations

import boto3
import click
from botocore.exceptions import ClientError

from lib.cli import cli
from lib.env import Config


@cli.group()
def ce_router():
    """CE Router emergency routing controls."""
    pass


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


@ce_router.command("killswitch")
@click.option("--environment", "-e", help="Environment to enable (prod, staging, beta). Default: all")
@click.option("--skip-confirmation", is_flag=True, default=False, help="Skip confirmation prompt")
@click.pass_obj
def killswitch(cfg: Config, environment: str | None, skip_confirmation: bool):
    """
    EMERGENCY: Route compilation traffic to CE Router instances.

    This immediately enables ALB routing to ce-router instances,
    bypassing Lambda or other routing for compilation requests.

    Examples:
        ce ce-router killswitch              # Enable for all environments
        ce ce-router killswitch -e prod      # Enable for production only
        ce ce-router killswitch -e staging   # Enable for staging only
    """
    click.echo("🚨 CE ROUTER EMERGENCY KILLSWITCH")
    click.echo("")

    if environment:
        click.echo(f"This will IMMEDIATELY route {environment} compilation traffic to CE Router instances.")
    else:
        click.echo("This will IMMEDIATELY route ALL compilation traffic to CE Router instances.")

    click.echo("Affected paths: /api/compiler/*/compile, /api/compiler/*/cmake")
    click.echo("")

    if not skip_confirmation and not click.confirm("Enable emergency CE Router routing?"):
        click.echo("Operation cancelled.")
        return

    alb_client = _get_alb_client()

    # Find ce-router target groups
    click.echo("🔍 Finding ce-router target groups...")
    target_groups = _find_ce_router_target_groups(alb_client)
    if not target_groups:
        click.echo("❌ Error: No ce-router target groups found", err=True)
        return

    # Filter by environment if specified
    if environment:
        if environment not in target_groups:
            click.echo(f"❌ Error: ce-router-{environment} target group not found", err=True)
            return
        target_groups = {environment: target_groups[environment]}

    # Find HTTPS listener
    click.echo("🔍 Finding HTTPS listener...")
    listener_arn = _find_compiler_explorer_listener(alb_client)
    if not listener_arn:
        return

    # Find or create ce-router rules
    click.echo("🔍 Finding/creating ce-router ALB rules...")
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

        click.echo(f"🚀 Enabling ce-router ALB routing for {env}...")
        if _enable_ce_router_rule(alb_client, env, rule_arn):
            click.echo(f"✅ {env.upper()} ce-router routing ACTIVATED")
            success_count += 1
        else:
            click.echo(f"❌ Failed to enable ce-router routing for {env}", err=True)

    if success_count > 0:
        click.echo("")
        click.echo(f"🎯 Compilation traffic for {success_count} environment(s) now routed to CE Router instances.")
    else:
        click.echo("")
        click.echo("❌ No environments were successfully enabled.", err=True)


@ce_router.command("disable")
@click.option("--skip-confirmation", is_flag=True, default=False, help="Skip confirmation prompt")
@click.pass_obj
def disable(cfg: Config, skip_confirmation: bool):
    """
    Disable CE Router routing, returning to default behavior.

    This disables the ce-router ALB rule, allowing traffic to fall back
    to whatever routing is configured as default (Lambda or instances).

    Example:
        ce ce-router disable
    """
    click.echo("🟡 DISABLE CE Router routing")
    click.echo("")
    click.echo("This will IMMEDIATELY disable ce-router routing.")
    click.echo("Traffic will fall back to default routing (Lambda or instances).")
    click.echo("")

    if not skip_confirmation and not click.confirm("Disable CE Router routing?"):
        click.echo("Operation cancelled.")
        return

    alb_client = _get_alb_client()

    # Find ce-router target groups
    click.echo("🔍 Finding ce-router target groups...")
    target_groups = _find_ce_router_target_groups(alb_client)
    if not target_groups:
        click.echo("❌ Error: No ce-router target groups found", err=True)
        return

    # Find HTTPS listener
    click.echo("🔍 Finding HTTPS listener...")
    listener_arn = _find_compiler_explorer_listener(alb_client)
    if not listener_arn:
        return

    # Find or create ce-router rules
    click.echo("🔍 Finding ce-router ALB rules...")
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

        click.echo(f"🚫 Disabling ce-router ALB routing for {env}...")
        if _disable_ce_router_rule(alb_client, env, rule_arn):
            click.echo(f"✅ {env.upper()} ce-router routing DISABLED")
            success_count += 1
        else:
            click.echo(f"❌ Failed to disable ce-router routing for {env}", err=True)

    if success_count > 0:
        click.echo("")
        click.echo(
            f"🎯 CE Router routing disabled for {success_count} environment(s). Traffic returned to default routing."
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

            except Exception as e:
                click.echo(f"         | Target health: Error ({e})")

            click.echo("")  # Add spacing between environments

    except Exception as e:
        click.echo(f"CE-ROUTER | ❌ ERROR: {str(e)}")
