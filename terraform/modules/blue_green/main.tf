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
    # Ignore changes to desired_capacity since it's managed by blue-green deployment
    ignore_changes = [desired_capacity]
  }

  name                      = "${var.environment}-${each.value}"
  default_cooldown          = var.default_cooldown
  health_check_grace_period = var.health_check_grace_period
  health_check_type         = "ELB"

  launch_template {
    id      = var.launch_template_id
    version = "$Latest"
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
