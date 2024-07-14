resource "aws_autoscaling_group" "aarch64prod-mixed" {
  lifecycle {
    create_before_destroy = true
  }

  default_cooldown          = local.cooldown
  health_check_grace_period = local.grace_period
  health_check_type         = "ELB"
  max_size                  = 4
  min_size                  = 1
  name                      = "aarch64prod"
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
        launch_template_id = aws_launch_template.CompilerExplorer-aarch64prod.id
        version            = "$Latest"
      }
      override {
        instance_type = "r7g.medium"
      }
    }
  }

  enabled_metrics = local.common_enabled_metrics

  target_group_arns = [aws_alb_target_group.ce["aarch64prod"].arn]
}

resource "aws_autoscaling_policy" "aarch64prod-mixed" {
  lifecycle {
    create_before_destroy = true
  }

  autoscaling_group_name    = aws_autoscaling_group.aarch64prod-mixed.name
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

resource "aws_autoscaling_group" "aarch64staging-mixed" {
  lifecycle {
    create_before_destroy = true
  }

  default_cooldown          = local.cooldown
  health_check_grace_period = local.grace_period
  health_check_type         = "ELB"
  max_size                  = 4
  min_size                  = 1
  name                      = "aarch64staging"
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
        launch_template_id = aws_launch_template.CompilerExplorer-aarch64staging.id
        version            = "$Latest"
      }
      override {
        instance_type = "r7g.medium"
      }
    }
  }

  enabled_metrics = local.common_enabled_metrics

  target_group_arns = [aws_alb_target_group.ce["aarch64staging"].arn]
}
