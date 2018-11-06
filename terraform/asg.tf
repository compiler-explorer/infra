locals {
  subnets = [
    "${aws_subnet.ce-1a.id}",
    "${aws_subnet.ce-1b.id}",
    "${aws_subnet.ce-1c.id}",
    "${aws_subnet.ce-1d.id}",
    "${aws_subnet.ce-1e.id}",
    "${aws_subnet.ce-1f.id}"
  ]
}

resource "aws_autoscaling_group" "nonspot-prod" {
  health_check_grace_period = 500
  health_check_type = "ELB"
  launch_configuration = "${aws_launch_configuration.CompilerExplorer-prod-t3.id}"
  max_size = 6
  min_size = 1
  name = "prod"
  vpc_zone_identifier = [
    "${local.subnets}"
  ]

  tag {
    key = "App"
    value = "GccExplorer"
    propagate_at_launch = true
  }

  tag {
    key = "Name"
    value = "Prod"
    propagate_at_launch = true
  }

  tag {
    key = "Site"
    value = "CompilerExplorer"
    propagate_at_launch = true
  }
  target_group_arns = [
    "${aws_alb_target_group.prod.arn}"
  ]
}

// TODO: consider a new scaling policy. e.g. "target tracking"
//resource "aws_autoscaling_policy" "compiler-explorer-nonspot-prod-scale-up" {
//  autoscaling_group_name = "${aws_autoscaling_group.nonspot-prod.name}"
//  name = "ce-increase-nonspot"
//  scaling_adjustment = 1
//  adjustment_type = "SimpleScaling"
//  estimated_instance_warmup = 1000
//  cooldown = 500
//}
//
//resource "aws_autoscaling_policy" "compiler-explorer-nonspot-prod-scale-down" {
//  autoscaling_group_name = "${aws_autoscaling_group.nonspot-prod.name}"
//  name = "ce-increase-nonspot"
//  scaling_adjustment = -1
//  adjustment_type = "SimpleScaling"
//  estimated_instance_warmup = 1000
//  cooldown = 500
//}
//
//resource "aws_cloudwatch_metric_alarm" "compiler-explorer-cpu-load-high" {
//  alarm_name = "compiler-explorer-cpu-load-high"
//  comparison_operator = "GreaterThanOrEqualToThreshold"
//  threshold = 40
//  evaluation_periods = 4
//  metric_name = "CPUUtilization"
//  namespace = "AWS/EC2"
//  period = 300
//  statistic = "Average"
//
//  dimensions {
//    AutoScalingGroupName = "${aws_autoscaling_group.nonspot-prod.arn}"
//  }
//
//  alarm_description = "Scale up Compiler Explorer when CPU load is high"
//  alarm_actions = [
//    "${aws_autoscaling_policy.compiler-explorer-nonspot-prod-scale-down.arn}"]
//}
//
//// This is actually an alarm on >= 10%, with an "if it's ok" setting to reduce the group size.
//// This gives us some hysteresis between scaling up and scaling down.
//resource "aws_cloudwatch_metric_alarm" "compiler-explorer-cpu-load-low" {
//  alarm_name = "compiler-explorer-cpu-load-low"
//  comparison_operator = "GreaterThanOrEqualToThreshold"
//  threshold = 10
//  evaluation_periods = 1
//  metric_name = "CPUUtilization"
//  namespace = "AWS/EC2"
//  period = 900
//  statistic = "Average"
//
//  dimensions {
//    AutoScalingGroupName = "${aws_autoscaling_group.nonspot-prod.arn}"
//  }
//
//  alarm_description = "Scale down Compiler Explorer when load returns to normal"
//  ok_actions = [
//    "${aws_autoscaling_policy.compiler-explorer-nonspot-prod-scale-down.arn}"]
//}

resource "aws_autoscaling_group" "spot-beta" {
  desired_capacity = 1
  health_check_grace_period = 500
  health_check_type = "EC2"
  launch_configuration = "${aws_launch_configuration.CompilerExplorer-beta-c5.id}"
  max_size = 4
  min_size = 0
  name = "spot-beta"
  vpc_zone_identifier = [
    "${local.subnets}"
  ]
  tag {
    key = "Environment"
    value = "Beta"
    propagate_at_launch = true
  }

  tag {
    key = "Name"
    value = "Beta"
    propagate_at_launch = true
  }

  tag {
    key = "Site"
    value = "CompilerExplorer"
    propagate_at_launch = true
  }
  target_group_arns = [
    "${aws_alb_target_group.beta.arn}"
  ]
}

resource "aws_autoscaling_group" "spot-prod" {
  desired_capacity = 1
  health_check_grace_period = 500
  health_check_type = "ELB"
  launch_configuration = "${aws_launch_configuration.CompilerExplorer-prod-c5.id}"
  max_size = 4
  min_size = 0
  name = "spot-prod"
  vpc_zone_identifier = [
    "${local.subnets}"
  ]

  tag {
    key = "Name"
    value = "Prod"
    propagate_at_launch = true
  }

  tag {
    key = "Site"
    value = "CompilerExplorer"
    propagate_at_launch = true
  }
  target_group_arns = [
    "${aws_alb_target_group.prod.arn}"
  ]
}
