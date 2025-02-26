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
    aws_autoscaling_group.prod-mixed.name,
    aws_autoscaling_group.gpu.name,
    aws_autoscaling_group.staging.name,
    aws_autoscaling_group.beta.name,
    aws_autoscaling_group.winprod-mixed.name,
    aws_autoscaling_group.aarch64prod-mixed
  ]
  notifications = [
    "autoscaling:EC2_INSTANCE_TERMINATE"
  ]

  topic_arn = aws_sns_topic.elb-instance-terminate.arn
}
