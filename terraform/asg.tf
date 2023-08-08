locals {
  subnets      = local.all_subnet_ids
  // As of Aug 8th 2023, starts could take >2m30
  grace_period = 60*3
  cooldown     = 180
  win_grace_period = 300
}

resource "aws_autoscaling_group" "prod-mixed" {
  lifecycle {
    create_before_destroy = true
  }

  default_cooldown          = local.cooldown
  health_check_grace_period = local.grace_period
  health_check_type         = "ELB"
  max_size                  = 24
  min_size                  = 2
  // Made two after @apmorton suggestion to cover edge cases of "last node unhealthy"
  name                      = "prod"
  vpc_zone_identifier       = local.subnets

  mixed_instances_policy {
    instances_distribution {
      // This base value is zero so we don't have any non-spot instances. We may wish to bump this if we have issues
      // getting spot capacity.
      on_demand_allocation_strategy            = "lowest-price"
      on_demand_base_capacity                  = 0
      on_demand_percentage_above_base_capacity = 0
      spot_allocation_strategy                 = "price-capacity-optimized"
      spot_instance_pools                      = 0
    }
    launch_template {
      launch_template_specification {
        launch_template_id = aws_launch_template.CompilerExplorer-prod.id
        version            = "$Latest"
      }
      // As of March 14 2023, we started seeing EFS issues running out of burst credit. We believe it's to do with
      // machines no longer having enough RAM to reasonably FS cache on top of all the other stuff they're doing.
      // We're bumping to m* instances from c* to give us more headroom.
      override {
        instance_type = "m5zn.large"
      }
      override {
        instance_type = "m5.large"
      }
      override {
        instance_type = "m5n.large"
      }
      override {
        instance_type = "m5d.large"
      }
      override {
        instance_type = "m5a.large"
      }
      override {
        instance_type = "m5ad.large"
      }
      override {
        instance_type = "m6a.large"
      }
      override {
        instance_type = "m6i.large"
      }
      override {
        instance_type = "m6id.large"
      }
      override {
        instance_type = "m6in.large"
      }
    }
  }

  enabled_metrics = [
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

  target_group_arns = [aws_alb_target_group.ce["prod"].arn]
}

resource "aws_autoscaling_policy" "prod-mixed" {
  lifecycle {
    create_before_destroy = true
  }

  autoscaling_group_name    = aws_autoscaling_group.prod-mixed.name
  name                      = "cpu-tracker"
  policy_type               = "TargetTrackingScaling"
  estimated_instance_warmup = local.grace_period + 30
  target_tracking_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ASGAverageCPUUtilization"
    }
    target_value = 50.0
  }
}

resource "aws_autoscaling_group" "beta" {
  lifecycle {
    create_before_destroy = true
  }

  default_cooldown          = local.cooldown
  health_check_grace_period = local.grace_period
  health_check_type         = "ELB"
  launch_template {
    id      = aws_launch_template.CompilerExplorer-beta.id
    version = "$Latest"
  }

  max_size            = 4
  min_size            = 0
  name                = "beta"
  vpc_zone_identifier = local.subnets

  target_group_arns = [aws_alb_target_group.ce["beta"].arn]
}

resource "aws_autoscaling_group" "staging" {
  lifecycle {
    create_before_destroy = true
  }

  default_cooldown          = local.cooldown
  health_check_grace_period = local.grace_period
  health_check_type         = "ELB"
  launch_template {
    id      = aws_launch_template.CompilerExplorer-staging.id
    version = "$Latest"
  }
  max_size            = 4
  min_size            = 0
  name                = "staging"
  vpc_zone_identifier = local.subnets

  target_group_arns = [aws_alb_target_group.ce["staging"].arn]
}

resource "aws_autoscaling_group" "wintest" {
  lifecycle {
    create_before_destroy = true
  }

  default_cooldown          = local.cooldown
  // override grace period until everything works
  health_check_grace_period = 300
  health_check_type         = "ELB"
  launch_template {
    id      = aws_launch_template.CompilerExplorer-wintest.id
    version = "$Latest"
  }
  max_size            = 4
  min_size            = 0
  name                = "wintest"
  vpc_zone_identifier = local.subnets

  target_group_arns = [aws_alb_target_group.ce["wintest"].arn]
}

resource "aws_autoscaling_group" "winstaging" {
  lifecycle {
    create_before_destroy = true
  }

  default_cooldown          = local.cooldown
  // override grace period until everything works
  health_check_grace_period = 500
  health_check_type         = "ELB"
  launch_template {
    id      = aws_launch_template.CompilerExplorer-winstaging.id
    version = "$Latest"
  }
  max_size            = 4
  min_size            = 0
  name                = "winstaging"
  vpc_zone_identifier = local.subnets

  target_group_arns = [aws_alb_target_group.ce["winstaging"].arn]
}

resource "aws_autoscaling_group" "gpu" {
  lifecycle {
    create_before_destroy = true
  }

  default_cooldown          = local.cooldown
  health_check_grace_period = local.grace_period
  health_check_type         = "ELB"
  max_size                  = 4
  min_size                  = 2
  name                      = "gpu"
  vpc_zone_identifier       = local.subnets

  mixed_instances_policy {
    instances_distribution {
      on_demand_allocation_strategy            = "prioritized"
      // We need to have at least one here or we seem to never get any capacity. This is expensive
      // but without it we get issues with autodiscovery if GPUs are down, and lots of alerts.
      on_demand_base_capacity                  = 1
      on_demand_percentage_above_base_capacity = 0
      spot_allocation_strategy                 = "price-capacity-optimized"
      spot_instance_pools                      = 0
    }
    launch_template {
      launch_template_specification {
        launch_template_id = aws_launch_template.CompilerExplorer-prod-gpu.id
        version            = "$Latest"
      }
      override {
        instance_type = "g4dn.xlarge"
      }
      override {
        instance_type = "g4dn.2xlarge"
      }
    }
  }

  enabled_metrics = [
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

  target_group_arns = [aws_alb_target_group.ce["gpu"].arn]
}


resource "aws_autoscaling_policy" "gpu" {
  lifecycle {
    create_before_destroy = true
  }

  autoscaling_group_name    = aws_autoscaling_group.gpu.name
  name                      = "cpu-tracker"
  policy_type               = "TargetTrackingScaling"
  estimated_instance_warmup = local.grace_period + 30
  target_tracking_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ASGAverageCPUUtilization"
    }
    target_value = 50.0
  }
}

resource "aws_autoscaling_group" "winprod-mixed" {
  lifecycle {
    create_before_destroy = true
  }

  default_cooldown          = local.cooldown
  health_check_grace_period = local.win_grace_period
  health_check_type         = "ELB"
  max_size                  = 4
  min_size                  = 1
  name                      = "winprod"
  vpc_zone_identifier       = local.subnets

  mixed_instances_policy {
    instances_distribution {
      on_demand_allocation_strategy            = "lowest-price"
      on_demand_base_capacity                  = 0
      on_demand_percentage_above_base_capacity = 0
      spot_allocation_strategy                 = "price-capacity-optimized"
      spot_instance_pools                      = 0
    }
    launch_template {
      launch_template_specification {
        launch_template_id = aws_launch_template.CompilerExplorer-winprod.id
        version            = "$Latest"
      }

      // instance types were chosen based on 8g mem, 2vcpu, >= 3ghz, >= 10 gigabit
      override {
        instance_type = "m5zn.large"
      }
      override {
        instance_type = "m5.large"
      }
      override {
        instance_type = "m5n.large"
      }
      override {
        instance_type = "m6i.large"
      }
      override {
        instance_type = "m6id.large"
      }
      override {
        instance_type = "m6in.large"
      }
    }
  }

  enabled_metrics = [
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

  target_group_arns = [aws_alb_target_group.ce["winprod"].arn]
}

resource "aws_autoscaling_policy" "winprod-mixed" {
  lifecycle {
    create_before_destroy = true
  }

  autoscaling_group_name    = aws_autoscaling_group.winprod-mixed.name
  name                      = "cpu-tracker"
  policy_type               = "TargetTrackingScaling"
  estimated_instance_warmup = local.grace_period + 30
  target_tracking_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ASGAverageCPUUtilization"
    }
    target_value = 70.0
  }
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
  ]
  notifications = [
    "autoscaling:EC2_INSTANCE_TERMINATE"
  ]

  topic_arn = aws_sns_topic.elb-instance-terminate.arn
}
