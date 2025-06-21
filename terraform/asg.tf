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
