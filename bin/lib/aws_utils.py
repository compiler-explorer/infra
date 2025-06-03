"""General AWS utility functions for Compiler Explorer infrastructure."""

from typing import Any, Dict, List, Optional

from botocore.exceptions import ClientError

from lib.amazon import as_client, ec2_client, elb_client


def get_instance_private_ip(instance_id: str) -> Optional[str]:
    """Get the private IP address of an EC2 instance."""
    try:
        response = ec2_client.describe_instances(InstanceIds=[instance_id])
        if response["Reservations"] and response["Reservations"][0]["Instances"]:
            instance = response["Reservations"][0]["Instances"][0]
            if instance["State"]["Name"] == "running":
                return instance.get("PrivateIpAddress")
    except Exception:
        pass
    return None


def get_asg_info(asg_name: str) -> Optional[Dict[str, Any]]:
    """Get ASG information or return None if not found."""
    try:
        response = as_client.describe_auto_scaling_groups(AutoScalingGroupNames=[asg_name])
        if response["AutoScalingGroups"]:
            return response["AutoScalingGroups"][0]
    except ClientError:
        pass
    return None


def get_target_health_counts(target_group_arn: str, instance_ids: List[str]) -> Dict[str, int]:
    """Get counts of healthy and unused instances in a target group."""
    try:
        tg_health = elb_client.describe_target_health(
            TargetGroupArn=target_group_arn, Targets=[{"Id": iid} for iid in instance_ids]
        )
        healthy_count = 0
        unused_count = 0

        for target in tg_health["TargetHealthDescriptions"]:
            state = target["TargetHealth"]["State"]
            if state == "healthy":
                healthy_count += 1
            elif state == "unused":
                unused_count += 1

        return {"healthy": healthy_count, "unused": unused_count}
    except Exception:
        return {"healthy": 0, "unused": 0}


def scale_asg(asg_name: str, desired_capacity: int, set_min_size: bool = False) -> None:
    """Scale an ASG to the specified capacity.

    Args:
        asg_name: Name of the Auto Scaling Group
        desired_capacity: Target number of instances
        set_min_size: If True, also sets MinSize to match desired_capacity
    """
    print(f"Scaling {asg_name} to {desired_capacity} instances")

    if set_min_size:
        # Set both desired capacity and min size to prevent scale-down during deployment
        print(f"  Also setting minimum size to {desired_capacity} to prevent scale-down")
        as_client.update_auto_scaling_group(
            AutoScalingGroupName=asg_name, MinSize=desired_capacity, DesiredCapacity=desired_capacity
        )
    else:
        as_client.set_desired_capacity(AutoScalingGroupName=asg_name, DesiredCapacity=desired_capacity)


def reset_asg_min_size(asg_name: str, min_size: int = 0) -> None:
    """Reset the minimum size of an ASG.

    Args:
        asg_name: Name of the Auto Scaling Group
        min_size: Minimum size to set (default: 0)
    """
    print(f"Resetting {asg_name} minimum size to {min_size}")
    as_client.update_auto_scaling_group(AutoScalingGroupName=asg_name, MinSize=min_size)
