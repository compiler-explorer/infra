variable "ce-target-groups" {
  description = "Target groups to create on port 80 for CE"
  default = {
    # All blue-green environments now use modules instead of single target groups
    # Keeping this variable structure for any remaining single environments
  }
}

resource "aws_alb_target_group" "ce" {
  for_each = var.ce-target-groups

  lifecycle {
    create_before_destroy = true
  }

  name     = title(each.key)
  port     = 80
  protocol = "HTTP"
  vpc_id   = module.ce_network.vpc.id
  // some time to kick off old connections
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
}

resource "aws_alb_target_group" "conan" {
  lifecycle {
    create_before_destroy = true
  }
  name                 = "ConanGroup"
  port                 = 1080
  protocol             = "HTTP"
  vpc_id               = module.ce_network.vpc.id
  deregistration_delay = 15
  health_check {
    path                = "/healthcheck"
    timeout             = 3
    unhealthy_threshold = 3
    healthy_threshold   = 2
    interval            = 5
    protocol            = "HTTP"
  }
  stickiness {
    type    = "lb_cookie"
    enabled = false
  }
}

resource "aws_alb_target_group_attachment" "CEConanServerTargetInstance" {
  target_group_arn = aws_alb_target_group.conan.id
  target_id        = aws_instance.ConanNode.id
  port             = 1080
}

# Target group for the status Lambda
resource "aws_alb_target_group" "lambda_status" {
  name        = "StatusApiTargetGroup"
  target_type = "lambda"
}

# Attach the Lambda function to the target group
resource "aws_alb_target_group_attachment" "lambda-status-endpoint" {
  target_group_arn = aws_alb_target_group.lambda_status.arn
  target_id        = aws_lambda_function.status.arn
  depends_on       = [aws_lambda_permission.from_alb_status]
}
