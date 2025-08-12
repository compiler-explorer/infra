#!/usr/bin/env python3

"""
CLI commands for managing compilation Lambda routing and killswitch functionality.
"""

import boto3
import click
from botocore.exceptions import ClientError

from lib.cli import cli
from lib.env import Config


@cli.group()
def compilation_lambda():
    """Manage compilation Lambda routing and emergency controls."""
    pass


def _get_alb_client():
    """Get ALB (ELBv2) client."""
    return boto3.client("elbv2")


def _find_listener_rule(alb_client, environment: str):
    """Find the ALB listener rule for the compilation Lambda environment."""
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
            return None, None

        # Get the HTTPS listener
        listeners_response = alb_client.describe_listeners(LoadBalancerArn=compiler_explorer_lb["LoadBalancerArn"])

        https_listener = None
        for listener in listeners_response["Listeners"]:
            if listener.get("Port") == 443:
                https_listener = listener
                break

        if not https_listener:
            click.echo("Error: Could not find HTTPS listener", err=True)
            return None, None

        # Get all rules for the HTTPS listener
        rules_response = alb_client.describe_rules(ListenerArn=https_listener["ListenerArn"])

        # Find the rule that matches our compilation Lambda paths (enabled or disabled)
        target_patterns = [
            f"/{environment}/api/compiler/*/compile",
            "/api/compiler/*/compile" if environment == "prod" else None,
            "/killswitch-disabled-*",  # Also look for disabled rules
        ]
        target_patterns = [p for p in target_patterns if p is not None]

        # First, try to find a rule for this environment's Lambda target group
        for rule in rules_response["Rules"]:
            if rule.get("Priority") == "default":
                continue

            # Check the rule's actions for Lambda target groups
            for action in rule.get("Actions", []):
                if action.get("Type") == "forward":
                    target_group_arn = action.get("TargetGroupArn", "")
                    # Look for compilation-lambda target groups for this environment
                    if f"compilation-lambda-{environment}" in target_group_arn or (
                        environment == "prod" and "compilation-lambda-prod" in target_group_arn
                    ):
                        return https_listener["ListenerArn"], rule

        # Fallback: look for rules with matching path patterns
        for rule in rules_response["Rules"]:
            if rule.get("Priority") == "default":
                continue

            # Check if this rule has path patterns that match our environment
            for condition in rule.get("Conditions", []):
                if condition.get("Field") == "path-pattern":
                    values = condition.get("Values", [])
                    for pattern in target_patterns:
                        if pattern in values:
                            return https_listener["ListenerArn"], rule

        click.echo(f"Warning: Could not find ALB listener rule for {environment} environment")
        return https_listener["ListenerArn"], None

    except ClientError as e:
        click.echo(f"Error finding ALB listener rule: {e}", err=True)
        return None, None


def _disable_listener_rule(alb_client, rule_arn: str) -> bool:
    """Disable an ALB listener rule by modifying its conditions to never match."""
    try:
        # Modify the rule to have an impossible condition
        alb_client.modify_rule(
            RuleArn=rule_arn,
            Conditions=[
                {
                    "Field": "path-pattern",
                    "Values": ["/killswitch-disabled-*"],  # Path that will never match
                }
            ],
        )
        return True
    except ClientError as e:
        click.echo(f"Error disabling listener rule: {e}", err=True)
        return False


def _enable_listener_rule(alb_client, rule_arn: str, environment: str) -> bool:
    """Re-enable an ALB listener rule by restoring its original conditions."""
    try:
        # Restore the original path patterns based on environment
        if environment == "prod":
            path_patterns = ["/api/compiler/*/compile", "/api/compiler/*/cmake"]
        else:
            path_patterns = [f"/{environment}/api/compiler/*/compile", f"/{environment}/api/compiler/*/cmake"]

        alb_client.modify_rule(RuleArn=rule_arn, Conditions=[{"Field": "path-pattern", "Values": path_patterns}])
        return True
    except ClientError as e:
        click.echo(f"Error enabling listener rule: {e}", err=True)
        return False


def _get_rule_status(rule) -> str:
    """Determine if a rule is active based on its conditions."""
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


@compilation_lambda.command("killswitch")
@click.argument("environment", type=click.Choice(["beta", "staging", "prod"]))
@click.option("--skip-confirmation", is_flag=True, default=False, help="Skip confirmation prompt")
@click.pass_obj
def killswitch(cfg: Config, environment: str, skip_confirmation: bool):
    """
    EMERGENCY: Disable compilation Lambda ALB routing for an environment.

    This directly modifies the ALB listener rule to stop routing to Lambda,
    causing traffic to immediately fall back to the old instance-based routing.

    Example:
        ce compilation-lambda killswitch beta
    """
    click.echo(f"🚨 COMPILATION LAMBDA KILLSWITCH for {environment.upper()} environment")
    click.echo("")
    click.echo("This will IMMEDIATELY disable the compilation Lambda ALB routing.")
    click.echo("Traffic will fall back to the old instance-based routing within seconds.")
    click.echo("")

    if not skip_confirmation and not click.confirm(f"Disable compilation Lambda routing for {environment}?"):
        click.echo("Operation cancelled.")
        return

    alb_client = _get_alb_client()

    # Find the ALB listener rule
    click.echo("🔍 Finding ALB listener rule...")
    listener_arn, rule = _find_listener_rule(alb_client, environment)

    if not rule:
        click.echo(f"Error: No ALB listener rule found for {environment} environment", err=True)
        return

    rule_arn = rule["RuleArn"]

    # Check current status
    current_status = _get_rule_status(rule)
    if current_status == "DISABLED":
        click.echo(f"⚠️  ALB rule for {environment} is already disabled")
        return

    # Disable the rule
    click.echo("🚫 Disabling ALB listener rule...")
    if _disable_listener_rule(alb_client, rule_arn):
        click.echo(f"✅ Compilation Lambda routing DISABLED for {environment}")
        click.echo("Traffic is now using the old instance-based routing.")
        click.echo(f"Rule ARN: {rule_arn}")
    else:
        click.echo("❌ Failed to disable ALB listener rule", err=True)


@compilation_lambda.command("enable")
@click.argument("environment", type=click.Choice(["beta", "staging", "prod"]))
@click.option("--skip-confirmation", is_flag=True, default=False, help="Skip confirmation prompt")
@click.pass_obj
def enable(cfg: Config, environment: str, skip_confirmation: bool):
    """
    Re-enable compilation Lambda ALB routing for an environment.

    This directly modifies the ALB listener rule to restore routing to Lambda.

    Example:
        ce compilation-lambda enable beta
    """
    click.echo(f"🟢 ENABLE compilation Lambda routing for {environment.upper()} environment")
    click.echo("")
    click.echo("This will IMMEDIATELY enable the compilation Lambda ALB routing.")
    click.echo("Traffic will be routed through the compilation Lambda system within seconds.")
    click.echo("")

    if not skip_confirmation and not click.confirm(f"Enable compilation Lambda routing for {environment}?"):
        click.echo("Operation cancelled.")
        return

    alb_client = _get_alb_client()

    # Find the ALB listener rule
    click.echo("🔍 Finding ALB listener rule...")
    listener_arn, rule = _find_listener_rule(alb_client, environment)

    if not rule:
        click.echo(f"Error: No ALB listener rule found for {environment} environment", err=True)
        return

    rule_arn = rule["RuleArn"]

    # Check current status
    current_status = _get_rule_status(rule)
    if current_status == "ENABLED":
        click.echo(f"⚠️  ALB rule for {environment} is already enabled")
        return

    # Enable the rule
    click.echo("✅ Enabling ALB listener rule...")
    if _enable_listener_rule(alb_client, rule_arn, environment):
        click.echo(f"✅ Compilation Lambda routing ENABLED for {environment}")
        click.echo("Traffic is now using the compilation Lambda system.")
        click.echo(f"Rule ARN: {rule_arn}")
    else:
        click.echo("❌ Failed to enable ALB listener rule", err=True)


@compilation_lambda.command("status")
@click.argument("environment", type=click.Choice(["beta", "staging", "prod"]), required=False)
@click.pass_obj
def status(cfg: Config, environment: str):
    """
    Show the current status of compilation Lambda ALB routing.

    This checks the actual ALB listener rules, not Terraform configuration.

    Example:
        ce compilation-lambda status
        ce compilation-lambda status beta
    """
    alb_client = _get_alb_client()
    environments_to_check = [environment] if environment else ["beta", "staging", "prod"]

    click.echo("📊 Compilation Lambda ALB Routing Status")
    click.echo("=" * 45)

    for env in environments_to_check:
        try:
            listener_arn, rule = _find_listener_rule(alb_client, env)

            if not rule:
                status_text = "🔴 NOT_FOUND (no ALB rule exists)"
                rule_info = "N/A"
            else:
                rule_status = _get_rule_status(rule)
                rule_arn_short = rule["RuleArn"].split("/")[-1]
                rule_priority = rule.get("Priority", "unknown")

                if rule_status == "ENABLED":
                    status_text = "🟢 ENABLED (Lambda routing active)"
                elif rule_status == "DISABLED":
                    status_text = "🚨 KILLSWITCH ACTIVE (using instance routing)"
                else:
                    status_text = f"🟡 {rule_status}"

                rule_info = f"Rule: {rule_arn_short} (Priority: {rule_priority})"

            click.echo(f"{env.upper():8} | {status_text}")
            if rule_info != "N/A":
                click.echo(f"         | {rule_info}")

        except Exception as e:
            click.echo(f"{env.upper():8} | ❌ ERROR: {str(e)}")
