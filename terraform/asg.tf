locals {
  subnets = local.all_subnet_ids
  // As of Oct 28th 2024, starts taking >3m now
  grace_period     = 60 * 4
  cooldown         = 180
  win_grace_period = 500

  common_enabled_metrics = [
    "GroupDesiredCapacity",
    "GroupInServiceCapacity",
    "GroupInServiceInstances",
    "GroupMaxSize",
    "GroupMinSize",
    "GroupPendingCapacity",
    "GroupPendingInstances",
    "GroupStandbyCapacity",
    "GroupStandbyInstances",
    "GroupTerminatingCapacity",
    "GroupTerminatingInstances",
    "GroupTotalCapacity",
    "GroupTotalInstances",
  ]
}

resource "aws_sns_topic" "elb-instance-terminate" {
  name = "ElbInstanceTerminate"
}

resource "aws_autoscaling_notification" "notify" {
  group_names = [
    # Blue-green ASGs will be added via their respective modules
    # This notification is now primarily handled by the blue-green modules
  ]
  notifications = [
    "autoscaling:EC2_INSTANCE_TERMINATE"
  ]

  topic_arn = aws_sns_topic.elb-instance-terminate.arn
}
