from __future__ import annotations

import time

import click
from botocore.exceptions import ClientError

from lib.amazon import (
    as_client,
    get_autoscaling_groups_for,
)
from lib.blue_green_deploy import BlueGreenDeployment
from lib.ce_utils import are_you_sure, describe_current_release, set_update_message
from lib.cli import cli
from lib.cloudfront_utils import invalidate_cloudfront_distributions
from lib.env import Config, Environment


@cli.group()
def environment():
    """Environment manipulation commands."""


@environment.command(name="status")
@click.pass_obj
def environment_status(cfg: Config):
    """Gets the status of an environment."""
    if cfg.env.supports_blue_green:
        # For blue-green environments, show which color is active
        deployment = BlueGreenDeployment(cfg)
        try:
            active_color = deployment.get_active_color()
            print(f"Blue-green environment - Active color: {active_color}")
        except (ClientError, RuntimeError):
            print("Blue-green environment - Unable to determine active color")

        for asg in get_autoscaling_groups_for(cfg):
            asg_name = asg["AutoScalingGroupName"]
            desired = asg["DesiredCapacity"]
            # Determine if this ASG is the active one
            color = asg_name.split("-")[-1]  # Extract 'blue' or 'green'
            try:
                is_active = color == active_color
                status = " (ACTIVE)" if is_active else " (INACTIVE)"
            except RuntimeError:
                status = ""
            print(f"Found ASG {asg_name} with desired instances {desired}{status}")
    else:
        # Legacy environments
        for asg in get_autoscaling_groups_for(cfg):
            print(f"Found ASG {asg['AutoScalingGroupName']} with desired instances {asg['DesiredCapacity']}")


@environment.command(name="start")
@click.pass_obj
def environment_start(cfg: Config):
    """Starts up an environment by ensure its ASGs have capacity."""
    if cfg.env.supports_blue_green:
        print(f"⚠️  WARNING: Environment '{cfg.env.value}' uses blue-green deployment.")
        print(f"Use 'ce --env {cfg.env.value} blue-green deploy' instead of 'environment start'.")
        print("This command is deprecated for blue-green environments.")
        return

    for asg in get_autoscaling_groups_for(cfg):
        group_name = asg["AutoScalingGroupName"]
        if asg["MinSize"] > 0:
            print(f"Skipping ASG {group_name} as it has a non-zero min size")
            continue
        prev = asg["DesiredCapacity"]
        if prev:
            print(f"Skipping ASG {group_name} as it has non-zero desired capacity")
            continue
        print(f"Updating {group_name} to have desired capacity 1 (from {prev})")
        as_client.update_auto_scaling_group(AutoScalingGroupName=group_name, DesiredCapacity=1)


@environment.command(name="refresh")
@click.option(
    "--min-healthy-percent",
    type=click.IntRange(min=0, max=100),
    metavar="PERCENT",
    help="While updating, ensure at least PERCENT are healthy",
    default=75,
    show_default=True,
)
@click.option(
    "--motd",
    type=str,
    default="Site is being updated",
    help="Set the message of the day used during refresh",
    show_default=True,
)
@click.option("--notify/--no-notify", help="Send GitHub notifications for newly released PRs", default=True)
@click.option(
    "--skip-cloudfront",
    is_flag=True,
    help="Skip CloudFront invalidation after refresh",
    default=False,
)
@click.pass_obj
def environment_refresh(cfg: Config, min_healthy_percent: int, motd: str, skip_cloudfront: bool, notify: bool):
    """Refreshes an environment.

    This replaces all the instances in the ASGs associated with an environment with
    new instances (with the latest code), while ensuring there are some left to handle
    the traffic while we update."""
    if cfg.env.supports_blue_green:
        print(f"⚠️  WARNING: Environment '{cfg.env.value}' uses blue-green deployment.")
        print(f"Use 'ce --env {cfg.env.value} blue-green deploy' instead of 'environment refresh'.")
        print("This command is deprecated for blue-green environments.")
        return

    set_update_message(cfg, motd)

    for asg in get_autoscaling_groups_for(cfg):
        group_name = asg["AutoScalingGroupName"]
        if asg["DesiredCapacity"] == 0:
            print(f"Skipping ASG {group_name} as it has a zero size")
            continue
        describe_state = as_client.describe_instance_refreshes(AutoScalingGroupName=group_name)
        existing_refreshes = [
            x for x in describe_state["InstanceRefreshes"] if x["Status"] in ("Pending", "InProgress")
        ]
        if existing_refreshes:
            refresh_id = existing_refreshes[0]["InstanceRefreshId"]
            print(f"  Found existing refresh {refresh_id} for {group_name}")
        else:
            if not are_you_sure(f"Refresh instances in {group_name} with version {describe_current_release(cfg)}", cfg):
                continue
            print("  Starting new refresh...")
            refresh_result = as_client.start_instance_refresh(
                AutoScalingGroupName=group_name, Preferences=dict(MinHealthyPercentage=min_healthy_percent)
            )
            refresh_id = refresh_result["InstanceRefreshId"]
            print(f"  id {refresh_id}")

        last_log = ""
        while True:
            time.sleep(5)
            describe_state = as_client.describe_instance_refreshes(
                AutoScalingGroupName=group_name, InstanceRefreshIds=[refresh_id]
            )
            refresh = describe_state["InstanceRefreshes"][0]
            status = refresh["Status"]
            if status == "InProgress":
                log = (
                    f"  {status}, {refresh['PercentageComplete']}%, "
                    f"{refresh['InstancesToUpdate']} to update. "
                    f"{refresh.get('StatusReason', '')}"
                )
            else:
                log = f"  Status: {status}"
            if log != last_log:
                print(log)
                last_log = log
            if status in ("Successful", "Failed", "Cancelled"):
                break
    # Note: Notifications are now handled by blue-green deployment system
    # For environments using blue-green deployment, use: ce blue-green deploy
    set_update_message(cfg, "")

    if not skip_cloudfront:
        invalidate_cloudfront_distributions(cfg)


@environment.command(name="clearmsg")
@click.pass_obj
def update_clearmsg(cfg: Config):
    """Clears the 'Site is being updated' message."""
    set_update_message(cfg, "")


@environment.command(name="invalidate-cloudfront")
@click.pass_obj
def environment_invalidate_cloudfront(cfg: Config):
    """Manually trigger CloudFront invalidations for an environment."""
    if are_you_sure(f"create CloudFront invalidations for {cfg.env.value}", cfg):
        invalidate_cloudfront_distributions(cfg)


@environment.command(name="stop")
@click.pass_obj
def environment_stop(cfg: Config):
    """Stops an environment."""
    if cfg.env.supports_blue_green:
        print(f"⚠️  WARNING: Environment '{cfg.env.value}' uses blue-green deployment.")
        print(f"Use 'ce --env {cfg.env.value} blue-green shutdown' instead of 'environment stop'.")
        print("This command is deprecated for blue-green environments.")
        return

    if cfg.env == Environment.PROD:
        print("Operation aborted. This would bring down the site")
        print("If you know what you are doing, edit the code in bin/lib/cli/environment.py, function environment_stop")
    elif are_you_sure("stop environment", cfg):
        for asg in get_autoscaling_groups_for(cfg):
            group_name = asg["AutoScalingGroupName"]
            if asg["MinSize"] > 0:
                print(f"Skipping ASG {group_name} as it has a non-zero min size")
                continue
            prev = asg["DesiredCapacity"]
            if not prev:
                print(f"Skipping ASG {group_name} as it already zero desired capacity")
                continue
            print(f"Updating {group_name} to have desired capacity 0 (from {prev})")
            as_client.update_auto_scaling_group(AutoScalingGroupName=group_name, DesiredCapacity=0)
