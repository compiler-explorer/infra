"""Blue-green deployment CLI commands."""

import json

import click

from lib.amazon import as_client
from lib.blue_green_deploy import BlueGreenDeployment
from lib.ce_utils import are_you_sure
from lib.cli import cli
from lib.env import Config


@cli.group(name="blue-green")
def blue_green():
    """Blue-green deployment commands (BETA - for testing only)."""
    pass


@blue_green.command(name="status")
@click.pass_obj
def blue_green_status(cfg: Config):
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
    for color, asg_info in status['asgs'].items():
        if 'error' in asg_info:
            print(f"  {color}: ERROR - {asg_info['error']}")
        else:
            active_marker = " (ACTIVE)" if color == status['active_color'] else ""
            print(f"  {color}{active_marker}:")
            print(f"    ASG Name: {asg_info['name']}")
            print(f"    Desired/Min/Max: {asg_info['desired']}/{asg_info['min']}/{asg_info['max']}")
            print(f"    Instances: {asg_info['healthy_instances']}/{asg_info['instances']} healthy")


@blue_green.command(name="deploy")
@click.option("--capacity", type=int, help="Target capacity for deployment (default: match current)")
@click.option("--skip-confirmation", is_flag=True, help="Skip confirmation prompt")
@click.pass_obj
def blue_green_deploy(cfg: Config, capacity: int, skip_confirmation: bool):
    """Deploy to the inactive color using blue-green strategy."""
    if cfg.env.value != "beta":
        print("Blue-green deployment is currently only available for beta environment")
        return
        
    deployment = BlueGreenDeployment(cfg)
    
    active = deployment.get_active_color()
    inactive = deployment.get_inactive_color()
    
    if not skip_confirmation:
        if not are_you_sure(
            f"deploy to {inactive} (currently active: {active})",
            cfg
        ):
            return
    
    try:
        deployment.deploy(target_capacity=capacity)
        print("\nDeployment successful!")
        print("Run 'ce blue-green rollback' if you need to revert")
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
        response = as_client.describe_auto_scaling_groups(
            AutoScalingGroupNames=[asg_name]
        )
        
        if not response['AutoScalingGroups'] or response['AutoScalingGroups'][0]['DesiredCapacity'] == 0:
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
            tg_arn = deployment.get_target_group_arn(color)
            print(f"✓ {color.capitalize()} target group exists")
        except Exception as e:
            issues.append(f"{color.capitalize()} target group not found: {e}")
    
    # Check ASGs
    for color in ["blue", "green"]:
        try:
            asg_name = deployment.get_asg_name(color)
            response = as_client.describe_auto_scaling_groups(
                AutoScalingGroupNames=[asg_name]
            )
            if response['AutoScalingGroups']:
                print(f"✓ {color.capitalize()} ASG exists: {asg_name}")
            else:
                issues.append(f"{color.capitalize()} ASG not found: {asg_name}")
        except Exception as e:
            issues.append(f"Error checking {color} ASG: {e}")
    
    # Check listener rule
    try:
        rule_arn = deployment.get_listener_rule_arn()
        if rule_arn:
            print(f"✓ ALB listener rule found")
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


@blue_green.command(name="test-scenario")
@click.argument("scenario", type=click.Choice(["happy-path", "rollback", "failure"]))
@click.pass_obj
def blue_green_test_scenario(cfg: Config, scenario: str):
    """Run a test scenario for blue-green deployment."""
    if cfg.env.value != "beta":
        print("Blue-green deployment is currently only available for beta environment")
        return
        
    print(f"\nRunning {scenario} test scenario...")
    
    if scenario == "happy-path":
        print("\nThis will:")
        print("1. Deploy to inactive color")
        print("2. Verify health")
        print("3. Switch traffic")
        print("4. Validate success")
        
        if are_you_sure("run happy-path test", cfg):
            # Implementation would go here
            print("Test scenario not yet implemented")
            
    elif scenario == "rollback":
        print("\nThis will:")
        print("1. Note current state")
        print("2. Deploy to inactive")
        print("3. Switch traffic")
        print("4. Simulate issue")
        print("5. Rollback")
        print("6. Verify rollback success")
        
        if are_you_sure("run rollback test", cfg):
            # Implementation would go here
            print("Test scenario not yet implemented")
            
    elif scenario == "failure":
        print("\nThis will:")
        print("1. Deploy with intentionally broken config")
        print("2. Verify failure handling")
        print("3. Ensure no traffic impact")
        
        if are_you_sure("run failure test", cfg):
            # Implementation would go here
            print("Test scenario not yet implemented")