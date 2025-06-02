# Blue-Green deployment infrastructure for Beta environment
# This is used for testing the blue-green deployment strategy before applying to production

# Blue target group for beta
resource "aws_alb_target_group" "beta_blue" {
  name     = "Beta-Blue"
  port     = 80
  protocol = "HTTP"
  vpc_id   = module.ce_network.vpc.id

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
    Environment = "beta"
    Color       = "blue"
  }
}

# Green target group for beta
resource "aws_alb_target_group" "beta_green" {
  name     = "Beta-Green"
  port     = 80
  protocol = "HTTP"
  vpc_id   = module.ce_network.vpc.id

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
    Environment = "beta"
    Color       = "green"
  }
}

# Blue ASG for beta
resource "aws_autoscaling_group" "beta_blue" {
  lifecycle {
    create_before_destroy = true
  }

  name                      = "beta-blue"
  default_cooldown          = local.cooldown
  health_check_grace_period = local.grace_period
  health_check_type         = "ELB"

  launch_template {
    id      = aws_launch_template.CompilerExplorer-beta.id
    version = "$Latest"
  }

  max_size            = 4
  min_size            = 0
  desired_capacity    = 0 # Start with zero capacity
  vpc_zone_identifier = local.subnets

  # Attach to blue target group
  target_group_arns = [aws_alb_target_group.beta_blue.arn]

  enabled_metrics = local.common_enabled_metrics

  tag {
    key                 = "Environment"
    value               = "beta"
    propagate_at_launch = true
  }

  tag {
    key                 = "Color"
    value               = "blue"
    propagate_at_launch = true
  }

  tag {
    key                 = "Name"
    value               = "CompilerExplorer-beta-blue"
    propagate_at_launch = true
  }
}

# Green ASG for beta
resource "aws_autoscaling_group" "beta_green" {
  lifecycle {
    create_before_destroy = true
  }

  name                      = "beta-green"
  default_cooldown          = local.cooldown
  health_check_grace_period = local.grace_period
  health_check_type         = "ELB"

  launch_template {
    id      = aws_launch_template.CompilerExplorer-beta.id
    version = "$Latest"
  }

  max_size            = 4
  min_size            = 0
  desired_capacity    = 0 # Start with zero capacity
  vpc_zone_identifier = local.subnets

  # Attach to green target group
  target_group_arns = [aws_alb_target_group.beta_green.arn]

  enabled_metrics = local.common_enabled_metrics

  tag {
    key                 = "Environment"
    value               = "beta"
    propagate_at_launch = true
  }

  tag {
    key                 = "Color"
    value               = "green"
    propagate_at_launch = true
  }

  tag {
    key                 = "Name"
    value               = "CompilerExplorer-beta-green"
    propagate_at_launch = true
  }
}

# SSM Parameter to track which color is active for beta
resource "aws_ssm_parameter" "beta_active_color" {
  name  = "/compiler-explorer/beta/active-color"
  type  = "String"
  value = "blue" # Initial value

  tags = {
    Environment = "beta"
    Purpose     = "blue-green-deployment"
  }
}

# SSM Parameter to track active target group ARN
resource "aws_ssm_parameter" "beta_active_target_group" {
  name  = "/compiler-explorer/beta/active-target-group-arn"
  type  = "String"
  value = aws_alb_target_group.beta_blue.arn # Initial value

  tags = {
    Environment = "beta"
    Purpose     = "blue-green-deployment"
  }
}

# Data source to read the active target group dynamically
data "aws_ssm_parameter" "beta_active_tg" {
  name = aws_ssm_parameter.beta_active_target_group.name
}

# Output values for reference
output "beta_blue_target_group_arn" {
  value       = aws_alb_target_group.beta_blue.arn
  description = "ARN of the beta blue target group"
}

output "beta_green_target_group_arn" {
  value       = aws_alb_target_group.beta_green.arn
  description = "ARN of the beta green target group"
}

output "beta_active_color" {
  value       = aws_ssm_parameter.beta_active_color.value
  description = "Currently active color for beta environment"
}