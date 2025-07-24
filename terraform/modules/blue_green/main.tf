# Blue-Green deployment module for Compiler Explorer
# Creates matching blue and green infrastructure for zero-downtime deployments

locals {
  colors = ["blue", "green"]

  # Capitalize function for consistent naming
  env_capitalized = title(var.environment)
}

# Target Groups for both colors
resource "aws_alb_target_group" "color" {
  for_each = toset(local.colors)

  name     = "${local.env_capitalized}-${title(each.value)}"
  port     = 80
  protocol = "HTTP"
  vpc_id   = var.vpc_id

  deregistration_delay          = 20
  load_balancing_algorithm_type = "least_outstanding_requests"

  health_check {
    path                = "/healthcheck"
    timeout             = 8
    unhealthy_threshold = 3
    healthy_threshold   = 2
    interval            = 10
    protocol            = "HTTP"
  }

  tags = {
    Environment = var.environment
    Color       = each.value
  }
}

# Auto Scaling Groups for both colors
resource "aws_autoscaling_group" "color" {
  for_each = toset(local.colors)

  lifecycle {
    create_before_destroy = true
    # Ignore changes to desired_capacity and min_size since they're managed by blue-green deployment
    ignore_changes = [desired_capacity, min_size]
  }

  name                      = "${var.environment}-${each.value}"
  default_cooldown          = var.default_cooldown
  health_check_grace_period = var.health_check_grace_period
  health_check_type         = "ELB"

  # Use either mixed instances policy or simple launch template
  dynamic "mixed_instances_policy" {
    for_each = var.use_mixed_instances_policy ? [1] : []
    content {
      instances_distribution {
        on_demand_allocation_strategy            = "lowest-price"
        on_demand_base_capacity                  = var.on_demand_base_capacity
        on_demand_percentage_above_base_capacity = var.on_demand_percentage_above_base_capacity
        spot_allocation_strategy                 = var.spot_allocation_strategy
        spot_instance_pools                      = 0
      }
      launch_template {
        launch_template_specification {
          launch_template_id = var.launch_template_id
          version            = "$Latest"
        }
        dynamic "override" {
          for_each = var.mixed_instances_overrides
          content {
            instance_type = override.value.instance_type
          }
        }
      }
    }
  }

  # Simple launch template when not using mixed instances
  dynamic "launch_template" {
    for_each = var.use_mixed_instances_policy ? [] : [1]
    content {
      id      = var.launch_template_id
      version = "$Latest"
    }
  }

  max_size            = var.asg_max_size
  min_size            = 0
  desired_capacity    = var.initial_desired_capacity
  vpc_zone_identifier = var.subnets

  # Attach to the corresponding target group
  target_group_arns = [aws_alb_target_group.color[each.value].arn]

  enabled_metrics = var.enabled_metrics

  tag {
    key                 = "Environment"
    value               = var.environment
    propagate_at_launch = true
  }

  tag {
    key                 = "Color"
    value               = each.value
    propagate_at_launch = true
  }

  tag {
    key                 = "Name"
    value               = "CompilerExplorer-${var.environment}-${each.value}"
    propagate_at_launch = true
  }
}

# SSM Parameter to track which color is active
resource "aws_ssm_parameter" "active_color" {
  lifecycle {
    # Ignore changes to value since it's managed by blue-green deployment
    ignore_changes = [value]
  }

  name  = "/compiler-explorer/${var.environment}/active-color"
  type  = "String"
  value = var.initial_active_color

  tags = {
    Environment = var.environment
    Purpose     = "blue-green-deployment"
  }
}

# SSM Parameter to track active target group ARN
resource "aws_ssm_parameter" "active_target_group" {
  lifecycle {
    # Ignore changes to value since it's managed by blue-green deployment
    ignore_changes = [value]
  }

  name  = "/compiler-explorer/${var.environment}/active-target-group-arn"
  type  = "String"
  value = aws_alb_target_group.color[var.initial_active_color].arn

  tags = {
    Environment = var.environment
    Purpose     = "blue-green-deployment"
  }
}

# Data source to read the active target group dynamically
data "aws_ssm_parameter" "active_tg" {
  name = aws_ssm_parameter.active_target_group.name
}

# Auto-scaling policies for both colors (if enabled)
resource "aws_autoscaling_policy" "color" {
  for_each = var.enable_autoscaling_policy ? toset(local.colors) : []

  lifecycle {
    create_before_destroy = true
  }

  autoscaling_group_name    = aws_autoscaling_group.color[each.value].name
  name                      = "cpu-tracker"
  policy_type               = "TargetTrackingScaling"
  estimated_instance_warmup = var.health_check_grace_period + 30

  target_tracking_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ASGAverageCPUUtilization"
    }
    target_value = var.autoscaling_target_cpu
  }
}
