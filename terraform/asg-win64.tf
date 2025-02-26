resource "aws_autoscaling_group" "wintest" {
  lifecycle {
    create_before_destroy = true
  }

  default_cooldown = local.cooldown
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

  default_cooldown = local.cooldown
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

resource "aws_autoscaling_group" "winprod-mixed" {
  lifecycle {
    create_before_destroy = true
  }

  default_cooldown          = local.cooldown
  health_check_grace_period = local.win_grace_period
  health_check_type         = "ELB"
  max_size                  = 8
  min_size                  = 2
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

  enabled_metrics = local.common_enabled_metrics

  target_group_arns = [aws_alb_target_group.ce["winprod"].arn]
}

resource "aws_autoscaling_policy" "winprod-mixed" {
  lifecycle {
    create_before_destroy = true
  }

  autoscaling_group_name    = aws_autoscaling_group.winprod-mixed.name
  name                      = "cpu-tracker"
  policy_type               = "TargetTrackingScaling"
  estimated_instance_warmup = local.grace_period + 60
  target_tracking_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ASGAverageCPUUtilization"
    }
    target_value = 40.0
  }
}
