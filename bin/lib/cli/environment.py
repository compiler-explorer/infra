import time

import click

from lib.amazon import get_autoscaling_groups_for, as_client
from lib.ce_utils import are_you_sure, describe_current_release
from lib.cli import cli
from lib.env import Config, Environment


@cli.group()
def environment():
    """Environment manipulation commands."""


@environment.command(name='status')
@click.pass_obj
def environment_status(cfg: Config):
    """Gets the status of an environment."""
    for asg in get_autoscaling_groups_for(cfg):
        print(f"Found ASG {asg['AutoScalingGroupName']} with desired instances {asg['DesiredCapacity']}")


@environment.command(name='start')
@click.pass_obj
def environment_start(cfg: Config):
    """Starts up an environment by ensure its ASGs have capacity."""
    for asg in get_autoscaling_groups_for(cfg):
        group_name = asg['AutoScalingGroupName']
        if asg['MinSize'] > 0:
            print(f"Skipping ASG {group_name} as it has a non-zero min size")
            continue
        prev = asg['DesiredCapacity']
        if prev:
            print(f"Skipping ASG {group_name} as it has non-zero desired capacity")
            continue
        print(f"Updating {group_name} to have desired capacity 1 (from {prev})")
        as_client.update_auto_scaling_group(AutoScalingGroupName=group_name, DesiredCapacity=1)


@environment.command(name='refresh')
@click.option("--min-healthy-percent", type=click.IntRange(min=0, max=100), metavar='PERCENT',
              help='While updating, ensure at least PERCENT are healthy', default=75, show_default=True)
@click.pass_obj
def environment_refresh(cfg: Config, min_healthy_percent: int):
    """Refreshes an environment.

    This replaces all the instances in the ASGs associated with an environment with
    new instances (with the latest code), while ensuring there are some left to handle
    the traffic while we update."""
    # TODO motd like the restart
    for asg in get_autoscaling_groups_for(cfg):
        group_name = asg['AutoScalingGroupName']
        if asg['DesiredCapacity'] == 0:
            print(f"Skipping ASG {group_name} as it has a zero size")
            continue
        describe_state = as_client.describe_instance_refreshes(
            AutoScalingGroupName=group_name
        )
        existing_refreshes = [x for x in describe_state['InstanceRefreshes'] if
                              x['Status'] in ('Pending', 'InProgress')]
        if existing_refreshes:
            refresh_id = existing_refreshes[0]['InstanceRefreshId']
            print(f"  Found existing refresh {refresh_id} for {group_name}")
        else:
            if not are_you_sure(f'Refresh instances in {group_name} with version {describe_current_release(cfg)}',
                                cfg):
                return
            print("  Starting new refresh...")
            refresh_result = as_client.start_instance_refresh(
                AutoScalingGroupName=group_name,
                Preferences=dict(MinHealthyPercentage=min_healthy_percent)
            )
            refresh_id = refresh_result['InstanceRefreshId']
            print(f"  id {refresh_id}")

        last_log = ""
        while True:
            time.sleep(5)
            describe_state = as_client.describe_instance_refreshes(
                AutoScalingGroupName=group_name,
                InstanceRefreshIds=[refresh_id]
            )
            refresh = describe_state['InstanceRefreshes'][0]
            status = refresh['Status']
            if status == 'InProgress':
                log = f"  {status}, {refresh['PercentageComplete']}%, " \
                      f"{refresh['InstancesToUpdate']} to update. " \
                      f"{refresh.get('StatusReason', '')}"
            else:
                log = f"  Status: {status}"
            if log != last_log:
                print(log)
                last_log = log
            if status in ('Successful', 'Failed', 'Cancelled'):
                break


@environment.command(name='stop')
@click.pass_obj
def environment_stop(cfg: Config):
    """Stops an environment."""
    if cfg.env == Environment.PROD:
        print('Operation aborted. This would bring down the site')
        print('If you know what you are doing, edit the code in bin/lib/ce.py, function environment_stop_cmd')
    elif are_you_sure('stop environment', cfg):
        for asg in get_autoscaling_groups_for(cfg):
            group_name = asg['AutoScalingGroupName']
            if asg['MinSize'] > 0:
                print(f"Skipping ASG {group_name} as it has a non-zero min size")
                continue
            prev = asg['DesiredCapacity']
            if not prev:
                print(f"Skipping ASG {group_name} as it already zero desired capacity")
                continue
            print(f"Updating {group_name} to have desired capacity 0 (from {prev})")
            as_client.update_auto_scaling_group(AutoScalingGroupName=group_name, DesiredCapacity=0)
