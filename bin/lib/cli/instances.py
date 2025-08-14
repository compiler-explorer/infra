import datetime
import logging
import shlex
import subprocess
import sys
import time
from typing import Dict, Sequence

import click

from lib.amazon import (
    as_client,
    ec2_client,
    elb_client,
    get_autoscaling_group,
    get_autoscaling_groups_for,
    target_group_arn_for,
)
from lib.blue_green_deploy import BlueGreenDeployment
from lib.ce_utils import (
    are_you_sure,
    describe_current_release,
    is_running_on_admin_node,
    set_update_message,
    wait_for_autoscale_state,
)
from lib.cli import cli
from lib.env import Config, Environment
from lib.instance import Instance, print_instances
from lib.ssh import exec_remote, exec_remote_all, run_remote_shell

LOGGER = logging.getLogger(__name__)


@cli.group()
def instances():
    """Instance management commands."""


@instances.command(name="exec_all")
@click.pass_obj
@click.argument("remote_cmd", required=True, nargs=-1)
def instances_exec_all(cfg: Config, remote_cmd: Sequence[str]):
    """Execute REMOTE_CMD on all the instances."""
    escaped = shlex.join(remote_cmd)
    if not are_you_sure(f"exec command {escaped} in all instances", cfg):
        return

    print("Running '{}' on all instances".format(escaped))
    exec_remote_all(pick_instances(cfg), remote_cmd)


@instances.command(name="login")
@click.pass_obj
def instances_login(cfg: Config):
    """Log in to one of the instances."""
    instance = pick_instance(cfg)
    run_remote_shell(instance)


@instances.command(name="restart_one")
@click.pass_obj
def instances_restart_one(cfg: Config):
    """Restart one of the instances."""
    instance = pick_instance(cfg)
    as_instance_status = instance.describe_autoscale()
    if not as_instance_status:
        LOGGER.error("Failed restarting %s - was not in ASG", instance)
        return
    as_group_name = as_instance_status["AutoScalingGroupName"]
    modified_groups: Dict[str, int] = {}
    try:
        restart_one_instance(as_group_name, instance, modified_groups)
    except RuntimeError as e:
        LOGGER.error("Failed restarting %s - skipping: %s", instance, e)


@instances.command(name="start")
@click.pass_obj
def instances_start(cfg: Config):
    """Start up the instances."""
    print("Starting version %s", describe_current_release(cfg))
    exec_remote_all(pick_instances(cfg), ["sudo", "systemctl", "start", "compiler-explorer"])


@instances.command(name="stop")
@click.pass_obj
def instances_stop(cfg: Config):
    """Stop the instances."""
    if cfg.env == Environment.PROD:
        print("Operation aborted. This would bring down the site")
        print("If you know what you are doing, edit the code in bin/lib/ce.py, function instances_stop_cmd")
    elif are_you_sure("stop all instances", cfg):
        exec_remote_all(pick_instances(cfg), ["sudo", "systemctl", "stop", "compiler-explorer"])


@instances.command(name="restart")
@click.option(
    "--motd",
    type=str,
    default="Site is being updated",
    help="Set the message of the day used during update",
    show_default=True,
)
@click.pass_obj
def instances_restart(cfg: Config, motd: str):
    """Restart the instances, picking up new code."""
    if not are_you_sure("restart all instances with version {}".format(describe_current_release(cfg)), cfg):
        return
    begin_time = datetime.datetime.now()
    # Store old motd
    set_update_message(cfg, motd)
    modified_groups: Dict[str, int] = {}
    failed = False
    to_restart = pick_instances(cfg)

    for index, instance in enumerate(to_restart):
        LOGGER.info("Restarting %s (%d of %d)...", instance, index + 1, len(to_restart))
        as_instance_status = instance.describe_autoscale()
        if not as_instance_status:
            LOGGER.warning("Skipping %s as it is no longer in the ASG", instance)
            continue
        as_group_name = as_instance_status["AutoScalingGroupName"]
        if as_instance_status["LifecycleState"] != "InService":
            LOGGER.warning("Skipping %s as it is not InService (%s)", instance, as_instance_status)
            continue

        try:
            restart_one_instance(as_group_name, instance, modified_groups)
        except RuntimeError as e:
            LOGGER.error("Failed restarting %s - skipping: %s", instance, e)
            failed = True
            # TODO, what here?

    for group, desired in iter(modified_groups.items()):
        LOGGER.info("Putting desired instances for %s back to %d", group, desired)
        as_client.update_auto_scaling_group(AutoScalingGroupName=group, DesiredCapacity=desired)
    set_update_message(cfg, "")
    end_time = datetime.datetime.now()
    delta_time = end_time - begin_time
    print(f"Instances restarted in {delta_time.total_seconds()} seconds")
    sys.exit(1 if failed else 0)


@instances.command(name="isolate")
@click.pass_obj
def instances_isolate(cfg: Config):
    """Isolate an instance for investigation (enable protections, remove from LB/ASG)."""
    instance = pick_instance(cfg)
    instance_id = instance.instance.instance_id

    as_instance_status = instance.describe_autoscale()
    if not as_instance_status:
        LOGGER.error("Failed isolating %s - was not in ASG", instance)
        return

    as_group_name = as_instance_status["AutoScalingGroupName"]

    if not are_you_sure(f"isolate instance {instance_id} for investigation", cfg):
        return

    print(f"Isolating instance {instance_id} for investigation...")

    try:
        LOGGER.info("Enabling stop protection for %s", instance)
        ec2_client.modify_instance_attribute(InstanceId=instance_id, DisableApiStop={"Value": False})

        LOGGER.info("Enabling termination protection for %s", instance)
        ec2_client.modify_instance_attribute(InstanceId=instance_id, DisableApiTermination={"Value": True})

        LOGGER.info("Enabling instance protection for %s", instance)
        as_client.set_instance_protection(
            AutoScalingGroupName=as_group_name, InstanceIds=[instance_id], ProtectedFromScaleIn=True
        )

        LOGGER.info("Putting %s into standby", instance)
        as_client.enter_standby(
            InstanceIds=[instance_id], AutoScalingGroupName=as_group_name, ShouldDecrementDesiredCapacity=False
        )
        wait_for_autoscale_state(instance, "Standby")

        LOGGER.info("Deregistering %s from target group", instance)
        elb_client.deregister_targets(TargetGroupArn=instance.group_arn, Targets=[{"Id": instance_id}])

        LOGGER.info("Waiting for instance to be deregistered from load balancer...")
        while True:
            health = elb_client.describe_target_health(TargetGroupArn=instance.group_arn, Targets=[{"Id": instance_id}])
            if not health["TargetHealthDescriptions"]:
                break
            state = health["TargetHealthDescriptions"][0]["TargetHealth"]["State"]
            if state == "unused":
                break
            LOGGER.debug("Deregistration state: %s", state)
            time.sleep(5)

        print(f"\n✅ Instance {instance_id} has been isolated successfully!")
        print("   - Stop protection: ENABLED")
        print("   - Termination protection: ENABLED")
        print("   - ASG state: Standby (not serving traffic)")
        print("   - Load balancer: Deregistered")
        print("\nYou can now investigate the instance:")
        print(f"   Private IP: {instance.instance.private_ip_address}")
        print(f"   Instance ID: {instance_id}")
        print("\nTo terminate this instance later, use: ce instances terminate-isolated")

    except Exception as e:
        LOGGER.error("Failed to isolate instance %s: %s", instance, e)
        print(f"❌ Error isolating instance: {e}")
        sys.exit(1)


@instances.command(name="terminate-isolated")
@click.pass_obj
def instances_terminate_isolated(cfg: Config):
    """Terminate an isolated instance and let ASG replace it."""
    instance = pick_instance(cfg)
    instance_id = instance.instance.instance_id

    as_instance_status = instance.describe_autoscale()
    if not as_instance_status:
        LOGGER.error("Instance %s is not in ASG", instance)
        return

    lifecycle_state = as_instance_status["LifecycleState"]
    if lifecycle_state != "Standby":
        print(f"Instance {instance_id} is not in isolated state (current state: {lifecycle_state})")
        print("Only instances in 'Standby' state can be terminated with this command.")
        return

    if not are_you_sure(f"terminate isolated instance {instance_id}", cfg):
        return

    print(f"Terminating isolated instance {instance_id}...")

    try:
        LOGGER.info("Removing termination protection for %s", instance)
        ec2_client.modify_instance_attribute(InstanceId=instance_id, DisableApiTermination={"Value": False})

        LOGGER.info("Removing stop protection for %s", instance)
        ec2_client.modify_instance_attribute(InstanceId=instance_id, DisableApiStop={"Value": False})

        LOGGER.info("Terminating instance %s", instance)
        ec2_client.terminate_instances(InstanceIds=[instance_id])

        print(f"\n✅ Instance {instance_id} has been terminated.")
        print("The ASG will automatically launch a replacement instance.")

    except Exception as e:
        LOGGER.error("Failed to terminate instance %s: %s", instance, e)
        print(f"❌ Error terminating instance: {e}")
        sys.exit(1)


@instances.command(name="status")
@click.pass_obj
def instances_status(cfg: Config):
    """Get the status of the instances."""
    if cfg.env.supports_blue_green:
        try:
            deployment = BlueGreenDeployment(cfg)

            blue_tg_arn = deployment.get_target_group_arn("blue")
            green_tg_arn = deployment.get_target_group_arn("green")
            active_color = deployment.get_active_color()

            print(f"Blue-Green Environment: {cfg.env.value}")
            print(f"Active Color: {active_color}")
            print()

            blue_instances = Instance.elb_instances(blue_tg_arn)
            if blue_instances:
                marker = " (ACTIVE)" if active_color == "blue" else ""
                print(f"Blue Instances{marker}:")
                print_instances(blue_instances, number=False)
            else:
                marker = " (ACTIVE)" if active_color == "blue" else ""
                print(f"Blue Instances{marker}: No instances")

            print()

            green_instances = Instance.elb_instances(green_tg_arn)
            if green_instances:
                marker = " (ACTIVE)" if active_color == "green" else ""
                print(f"Green Instances{marker}:")
                print_instances(green_instances, number=False)
            else:
                marker = " (ACTIVE)" if active_color == "green" else ""
                print(f"Green Instances{marker}: No instances")

            isolated_instances = get_isolated_instances_for_environment(cfg)
            if isolated_instances:
                print()
                print("Isolated Instances (in Standby for investigation):")
                print_instances(isolated_instances, number=False)

            if (blue_instances or green_instances or isolated_instances) and not is_running_on_admin_node():
                print()
                print("Note: Service and Version information requires SSH access from admin node.")

        except Exception as e:
            print(f"Error: Failed to get blue-green status for {cfg.env.value}: {e}")
    else:
        print(f"Environment: {cfg.env.value}")
        print_instances(Instance.elb_instances(target_group_arn_for(cfg)), number=False)

        isolated_instances = get_isolated_instances_for_environment(cfg)
        if isolated_instances:
            print()
            print("Isolated Instances (in Standby for investigation):")
            print_instances(isolated_instances, number=False)


def pick_instance(cfg: Config):
    elb_instances = get_instances_for_environment(cfg)
    isolated_instances = get_isolated_instances_for_environment(cfg)
    all_instances = elb_instances + isolated_instances

    if len(all_instances) == 1:
        return all_instances[0]
    while True:
        if elb_instances:
            print("Active instances:")
            print_instances(elb_instances, number=True)
        if isolated_instances:
            if elb_instances:
                print()
            print("Isolated instances (in Standby):")
            start_num = len(elb_instances)
            for i, inst in enumerate(isolated_instances):
                print(f"{start_num + i: <3}", end="")
                print_instances([inst], number=False)

        inst = input("Which instance? ")
        try:
            return all_instances[int(inst)]
        except (ValueError, IndexError):
            pass


def pick_instances(cfg: Config):
    elb_instances = get_instances_for_environment(cfg)
    isolated_instances = get_isolated_instances_for_environment(cfg)
    return elb_instances + isolated_instances


def get_instances_for_environment(cfg: Config):
    """Get instances for the environment, handling both blue-green and legacy deployments."""
    if cfg.env.supports_blue_green:
        try:
            deployment = BlueGreenDeployment(cfg)
            active_color = deployment.get_active_color()
            active_tg_arn = deployment.get_target_group_arn(active_color)

            return Instance.elb_instances(active_tg_arn)
        except Exception as e:
            raise RuntimeError(f"Failed to get instances for blue-green environment {cfg.env.value}: {e}") from e

    return Instance.elb_instances(target_group_arn_for(cfg))


def get_isolated_instances_for_environment(cfg: Config):
    """Get isolated (Standby) instances for the environment."""
    isolated_instances = []

    asgs = get_autoscaling_groups_for(cfg)

    for asg in asgs:
        asg_name = asg["AutoScalingGroupName"]

        asg_instances = as_client.describe_auto_scaling_instances(
            InstanceIds=[inst["InstanceId"] for inst in asg["Instances"]]
        )["AutoScalingInstances"]

        for asg_instance in asg_instances:
            if asg_instance["LifecycleState"] == "Standby":
                instance_id = asg_instance["InstanceId"]
                health = {"Target": {"Id": instance_id}, "TargetHealth": {"State": "unused"}}
                if cfg.env.supports_blue_green:
                    deployment = BlueGreenDeployment(cfg)
                    if "blue" in asg_name.lower():
                        group_arn = deployment.get_target_group_arn("blue")
                    else:
                        group_arn = deployment.get_target_group_arn("green")
                else:
                    group_arn = target_group_arn_for(cfg)

                isolated_instance = Instance(health, group_arn)
                isolated_instance.elb_health = "isolated"
                isolated_instances.append(isolated_instance)

    return isolated_instances


def restart_one_instance(as_group_name: str, instance: Instance, modified_groups: Dict[str, int]):
    instance_id = instance.instance.instance_id
    LOGGER.info("Enabling instance protection for %s", instance)
    as_client.set_instance_protection(
        AutoScalingGroupName=as_group_name, InstanceIds=[instance_id], ProtectedFromScaleIn=True
    )
    as_group = get_autoscaling_group(as_group_name)
    adjustment_required = as_group["DesiredCapacity"] == as_group["MinSize"]
    if adjustment_required:
        LOGGER.info("Group '%s' needs to be adjusted to keep enough nodes", as_group_name)
        modified_groups[as_group["AutoScalingGroupName"]] = as_group["DesiredCapacity"]
    LOGGER.info("Putting %s into standby", instance)
    as_client.enter_standby(
        InstanceIds=[instance_id],
        AutoScalingGroupName=as_group_name,
        ShouldDecrementDesiredCapacity=not adjustment_required,
    )
    wait_for_autoscale_state(instance, "Standby")
    LOGGER.info("Restarting service on %s", instance)
    restart_response = exec_remote(instance, ["sudo", "systemctl", "restart", "compiler-explorer"])
    if restart_response:
        LOGGER.warning("Restart gave some output: %s", restart_response)
    wait_for_healthok(instance)
    LOGGER.info("Moving %s out of standby", instance)
    as_client.exit_standby(InstanceIds=[instance_id], AutoScalingGroupName=as_group_name)
    wait_for_autoscale_state(instance, "InService")
    wait_for_elb_state(instance, "healthy")
    LOGGER.info("Disabling instance protection for %s", instance)
    as_client.set_instance_protection(
        AutoScalingGroupName=as_group_name, InstanceIds=[instance_id], ProtectedFromScaleIn=False
    )
    LOGGER.info("Instance restarted ok")


def wait_for_elb_state(instance, state):
    LOGGER.info("Waiting for %s to reach ELB state '%s'...", instance, state)
    while True:
        instance.update()
        instance_state = instance.instance.state["Name"]
        if instance_state != "running":
            raise RuntimeError("Instance no longer running (state {})".format(instance_state))
        LOGGER.debug("State is %s", instance.elb_health)
        if instance.elb_health == state:
            LOGGER.info("...done")
            return
        time.sleep(5)


def is_everything_awesome(instance):
    try:
        response = exec_remote(instance, ["curl", "-s", "--max-time", "2", "http://127.0.0.1/healthcheck"])
        return response.strip() == "Everything is awesome"
    except subprocess.CalledProcessError:
        return False


def wait_for_healthok(instance):
    LOGGER.info("Waiting for instance to be Online %s", instance)
    sys.stdout.write("Waiting")
    while not is_everything_awesome(instance):
        sys.stdout.write(".")
        # Flush stdout so tmux updates
        sys.stdout.flush()
        time.sleep(10)
    print("Ok, Everything is awesome!")
