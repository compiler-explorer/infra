locals {
  // 1e seems to be lacking many instance types..so I ignore it here
  subnets = [
    "${aws_subnet.ce-1a.id}",
    "${aws_subnet.ce-1b.id}",
    "${aws_subnet.ce-1c.id}",
    "${aws_subnet.ce-1d.id}",
    "${aws_subnet.ce-1f.id}"
  ]
}

resource "aws_autoscaling_group" "nonspot-prod" {
  health_check_grace_period = 500
  health_check_type         = "ELB"
  launch_configuration      = "${aws_launch_configuration.CompilerExplorer-prod-t3.id}"
  max_size                  = 6
  min_size                  = 1
  name                      = "prod"
  vpc_zone_identifier       = ["${local.subnets}"]

  tag {
    key                 = "App"
    value               = "GccExplorer"
    propagate_at_launch = true
  }

  tag {
    key                 = "Name"
    value               = "Prod"
    propagate_at_launch = true
  }

  tag {
    key                 = "Site"
    value               = "CompilerExplorer"
    propagate_at_launch = true
  }
  target_group_arns = ["${aws_alb_target_group.prod.arn}"]
  enabled_metrics   = [
    "GroupStandbyInstances",
    "GroupTotalInstances",
    "GroupPendingInstances",
    "GroupTerminatingInstances",
    "GroupDesiredCapacity",
    "GroupInServiceInstances",
    "GroupMinSize",
    "GroupMaxSize"
  ]
}

resource "aws_autoscaling_policy" "compiler-explorer-nonspot-prod" {
  lifecycle {
    create_before_destroy = true
  }

  autoscaling_group_name    = "${aws_autoscaling_group.nonspot-prod.name}"
  name                      = "cpu-tracker"
  policy_type               = "TargetTrackingScaling"
  estimated_instance_warmup = 1000
  target_tracking_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ASGAverageCPUUtilization"
    }
    target_value = 30.0
  }
}

resource "aws_autoscaling_group" "spot-beta" {
  lifecycle {
    create_before_destroy = true
  }

  health_check_grace_period = 500
  health_check_type         = "EC2"
  launch_configuration      = "${aws_launch_configuration.CompilerExplorer-beta-large.id}"
  max_size                  = 4
  min_size                  = 0
  name                      = "spot-beta"
  vpc_zone_identifier       = ["${local.subnets}"]
  tag {
    key                 = "Environment"
    value               = "Beta"
    propagate_at_launch = true
  }

  tag {
    key                 = "Name"
    value               = "Beta"
    propagate_at_launch = true
  }

  tag {
    key                 = "Site"
    value               = "CompilerExplorer"
    propagate_at_launch = true
  }
  target_group_arns = ["${aws_alb_target_group.beta.arn}"]
}

resource "aws_autoscaling_group" "spot-prod" {
  lifecycle {
    create_before_destroy = true
  }

  desired_capacity          = 1
  health_check_grace_period = 500
  health_check_type         = "ELB"
  launch_configuration      = "${aws_launch_configuration.CompilerExplorer-prod-spot-large.id}"
  max_size                  = 4
  min_size                  = 0
  name                      = "spot-prod"
  vpc_zone_identifier       = ["${local.subnets}"]

  tag {
    key                 = "Name"
    value               = "Prod"
    propagate_at_launch = true
  }

  tag {
    key                 = "Site"
    value               = "CompilerExplorer"
    propagate_at_launch = true
  }
  target_group_arns = ["${aws_alb_target_group.prod.arn}"]
}

resource "aws_autoscaling_group" "staging" {
  lifecycle {
    create_before_destroy = true
  }

  health_check_grace_period = 500
  health_check_type         = "EC2"
  launch_configuration      = "${aws_launch_configuration.CompilerExplorer-staging.id}"
  max_size                  = 4
  min_size                  = 0
  name                      = "staging"
  vpc_zone_identifier       = ["${local.subnets}"]
  tag {
    key                 = "Environment"
    value               = "Staging"
    propagate_at_launch = true
  }

  tag {
    key                 = "Name"
    value               = "Staging"
    propagate_at_launch = true
  }

  tag {
    key                 = "Site"
    value               = "CompilerExplorer"
    propagate_at_launch = true
  }
  target_group_arns = ["${aws_alb_target_group.staging.arn}"]
}
