# CE Router Module
# Auto Scaling Group and Load Balancer Target Group for CE Router instances

resource "aws_autoscaling_group" "ce_router" {
  name                      = "ce-router-${var.environment}"
  vpc_zone_identifier       = var.subnet_ids
  target_group_arns         = [aws_alb_target_group.ce_router.arn]
  health_check_type         = "ELB"
  health_check_grace_period = 300

  min_size         = var.min_size
  max_size         = var.max_size
  desired_capacity = var.desired_capacity

  launch_template {
    id      = var.launch_template_id
    version = "$Latest"
  }

  tag {
    key                 = "Name"
    value               = "CE-Router-${var.environment}"
    propagate_at_launch = true
  }

  tag {
    key                 = "Environment"
    value               = var.environment
    propagate_at_launch = true
  }

  tag {
    key                 = "Site"
    value               = "CompilerExplorer"
    propagate_at_launch = true
  }

  # Ensure instances are replaced before terminating old ones
  lifecycle {
    create_before_destroy = true
  }
}

# Target group for CE Router instances
resource "aws_alb_target_group" "ce_router" {
  name     = "ce-router-${var.environment}"
  port     = 80
  protocol = "HTTP"
  vpc_id   = var.vpc_id

  health_check {
    enabled             = true
    healthy_threshold   = 2
    interval            = 30
    matcher             = "200"
    path                = "/healthcheck"
    port                = "traffic-port"
    protocol            = "HTTP"
    timeout             = 5
    unhealthy_threshold = 3
  }

  # Sticky sessions not needed for routing service
  stickiness {
    enabled = false
    type    = "lb_cookie"
  }

  tags = {
    Name        = "CE-Router-${var.environment}"
    Site        = "CompilerExplorer"
    Environment = var.environment
  }
}

# Auto-attach ASG instances to target group
resource "aws_autoscaling_attachment" "ce_router" {
  autoscaling_group_name = aws_autoscaling_group.ce_router.id
  lb_target_group_arn    = aws_alb_target_group.ce_router.arn
}

# Target tracking scaling policy
resource "aws_autoscaling_policy" "ce_router_cpu_tracking" {
  name                   = "ce-router-${var.environment}-cpu-tracking"
  autoscaling_group_name = aws_autoscaling_group.ce_router.name
  policy_type            = "TargetTrackingScaling"

  target_tracking_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ASGAverageCPUUtilization"
    }
    target_value = 20.0
  }
}
