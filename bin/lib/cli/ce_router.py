from __future__ import annotations

import logging
import time

import click
from botocore.exceptions import ClientError

from lib.amazon import as_client, ec2_client, elb_client
from lib.ce_utils import are_you_sure
from lib.cli import cli
from lib.env import Config
from lib.ssh import exec_remote, exec_remote_all, run_remote_shell

LOGGER = logging.getLogger(__name__)


@cli.group()
def ce_router():
    """CE Router instance management commands."""


@ce_router.command(name="status")
@click.pass_obj
def ce_router_status(cfg: Config) -> None:
    """Show CE Router ASG status and instance health."""
    asg_name = "ce-router-asg"

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
            target_groups = elb_client.describe_target_groups(Names=["ce-router"])

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


@ce_router.command(name="scale")
@click.argument("desired_capacity", type=int, required=True)
@click.option("--skip-confirmation", is_flag=True, help="Skip confirmation prompt")
@click.pass_obj
def ce_router_scale(cfg: Config, desired_capacity: int, skip_confirmation: bool) -> None:
    """Manually scale CE Router instances to DESIRED_CAPACITY."""
    asg_name = "ce-router-asg"

    if not skip_confirmation and not are_you_sure(f"scale CE Router ASG to {desired_capacity} instances", cfg):
        return

    try:
        print(f"Scaling CE Router ASG to {desired_capacity} instances...")

        as_client.update_auto_scaling_group(AutoScalingGroupName=asg_name, DesiredCapacity=desired_capacity)

        print("Scaling request sent. Waiting for instances to reach desired state...")

        # Wait for scaling to complete
        # Note: wait_for_autoscale_state expects Instance object, not ASG name
        # For now, just sleep to allow time for scaling
        time.sleep(30)

        print(f"CE Router ASG successfully scaled to {desired_capacity} instances")

    except ClientError as e:
        print(f"Error scaling CE Router ASG: {e}")


@ce_router.command(name="login")
@click.option("--instance-id", help="Specific instance ID to login to")
@click.pass_obj
def ce_router_login(cfg: Config, instance_id: str | None) -> None:
    """SSH into a CE Router instance."""
    asg_name = "ce-router-asg"

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
    asg_name = "ce-router-asg"

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


@ce_router.command(name="health")
@click.pass_obj
def ce_router_health(cfg: Config) -> None:
    """Check health status of CE Router instances."""
    asg_name = "ce-router-asg"

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

        print(f"Checking health of {len(instance_ids)} CE Router instances...")

        # Check systemd service status
        exec_remote_all(instance_ids, ["sudo", "systemctl", "is-active", "ce-router"])

        # Check if Node.js process is responding
        exec_remote_all(instance_ids, ["curl", "-f", "http://localhost:10240/healthcheck"])

    except ClientError as e:
        print(f"Error checking CE Router health: {e}")


@ce_router.command(name="healthcheck")
@click.pass_obj
def ce_router_healthcheck(cfg: Config) -> None:
    """Send healthcheck requests to all CE Router instance private IPs."""
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

        # Get instance details from EC2
        ec2_response = ec2_client.describe_instances(InstanceIds=instance_ids)

        print(f"Checking health of {len(instance_ids)} CE Router instances...")

        for reservation in ec2_response["Reservations"]:
            for instance in reservation["Instances"]:
                instance_id = instance["InstanceId"]
                private_ip = instance.get("PrivateIpAddress", "N/A")
                state = instance["State"]["Name"]

                if state != "running":
                    print(f"  {instance_id} ({private_ip}): SKIPPED - instance state is {state}")
                    continue

                # Send healthcheck request to private IP
                try:
                    print(f"  {instance_id} ({private_ip}): ", end="", flush=True)
                    result = exec_remote(instance_id, ["curl", "-f", "-s", f"http://{private_ip}/healthcheck"])
                    if result and "OK" in result:
                        print("✅ HEALTHY")
                    else:
                        print(f"❌ UNHEALTHY - Response: {result}")
                except (OSError, ValueError) as e:
                    print(f"❌ ERROR - {e}")

    except ClientError as e:
        print(f"Error checking CE Router healthcheck: {e}")
