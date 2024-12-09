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
      on_demand_allocation_strategy = "prioritized"
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

  enabled_metrics = local.common_enabled_metrics

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
