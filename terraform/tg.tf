resource "aws_alb_target_group" "beta" {
  lifecycle {
    create_before_destroy = true
  }
  name                 = "Beta"
  port                 = 80
  protocol             = "HTTP"
  vpc_id               = aws_vpc.CompilerExplorer.id
  deregistration_delay = 15
  health_check {
    path                = "/healthcheck"
    timeout             = 5
    unhealthy_threshold = 2
    healthy_threshold   = 5
    interval            = 30
    protocol            = "HTTP"
  }
}

resource "aws_alb_target_group" "staging" {
  lifecycle {
    create_before_destroy = true
  }
  name                 = "Staging"
  port                 = 80
  protocol             = "HTTP"
  vpc_id               = aws_vpc.CompilerExplorer.id
  deregistration_delay = 15
  health_check {
    path                = "/healthcheck"
    timeout             = 3
    unhealthy_threshold = 3
    healthy_threshold   = 2
    interval            = 5
    protocol            = "HTTP"
  }
}

resource "aws_alb_target_group" "prod" {
  lifecycle {
    create_before_destroy = true
  }
  name                 = "Prod"
  port                 = 80
  protocol             = "HTTP"
  vpc_id               = aws_vpc.CompilerExplorer.id
  deregistration_delay = 15
  health_check {
    path                = "/healthcheck"
    timeout             = 3
    unhealthy_threshold = 3
    healthy_threshold   = 2
    interval            = 5
    protocol            = "HTTP"
  }
}

resource "aws_alb_target_group" "conan" {
  lifecycle {
    create_before_destroy = true
  }
  name                 = "Prod"
  port                 = 80
  protocol             = "HTTP"
  vpc_id               = aws_vpc.CompilerExplorer.id
  deregistration_delay = 15
  health_check {
    path                = "/healthcheck"
    timeout             = 3
    unhealthy_threshold = 3
    healthy_threshold   = 2
    interval            = 5
    protocol            = "HTTP"
  }
}

