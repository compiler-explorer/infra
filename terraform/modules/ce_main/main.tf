locals {
  ce-target-groups = concat(keys(var.extra_environments), ["prod"])
  grace_period = 180
  cooldown     = 180
}

resource "aws_alb_target_group" "ce" {
  for_each = toset(local.ce-target-groups)

  lifecycle {
    create_before_destroy = true
  }

  name                          = title(each.key)
  port                          = 80
  protocol                      = "HTTP"
  vpc_id                        = var.vpc_id
  // a minute to kick off old connections
  deregistration_delay          = 60
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

resource "aws_alb_listener" "compiler-explorer-alb-listen-http" {
  default_action {
    type             = "forward"
    target_group_arn = aws_alb_target_group.ce["prod"].arn
  }

  load_balancer_arn = aws_alb.GccExplorerApp.arn
  port              = 80
  protocol          = "HTTP"
}

resource "aws_alb_listener_rule" "http" {
  for_each     = var.extra_environments
  action {
    type             = "forward"
    target_group_arn = aws_alb_target_group.ce[each.key].arn
  }
  condition {
    path_pattern {
      values = ["/${each.key}*"]
    }
  }
  listener_arn = aws_alb_listener.compiler-explorer-alb-listen-http.arn
}

resource "aws_alb_listener" "compiler-explorer-alb-listen-https" {
  default_action {
    type             = "forward"
    target_group_arn = aws_alb_target_group.ce["prod"].arn
  }
  load_balancer_arn = aws_alb.GccExplorerApp.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-2015-05"
  certificate_arn   = var.https_certificate_arn
}

resource "aws_alb_listener_rule" "https" {
  for_each     = var.extra_environments
  action {
    type             = "forward"
    target_group_arn = aws_alb_target_group.ce[each.key].arn
  }
  condition {
    path_pattern {
      values = [
        "/${each.key}*"
      ]
    }
  }
  listener_arn = aws_alb_listener.compiler-explorer-alb-listen-https.arn
}

resource "aws_security_group" "CompilerExplorerAlb" {
  vpc_id      = var.vpc_id
  name        = "ce-alb-sg"
  description = "Load balancer security group"
  tags        = {
    Name = "CELoadBalancer"
  }
}

resource "aws_security_group_rule" "ALB_HttpsFromAnywhere" {
  security_group_id = aws_security_group.CompilerExplorerAlb.id
  type              = "ingress"
  from_port         = 443
  to_port           = 443
  cidr_blocks       = ["0.0.0.0/0"]
  ipv6_cidr_blocks  = ["::/0"]
  protocol          = "tcp"
  description       = "Allow HTTPS access from anywhere"
}

resource "aws_security_group_rule" "ALB_EgressToAnywhere" {
  security_group_id = aws_security_group.CompilerExplorerAlb.id
  type              = "egress"
  from_port         = 0
  to_port           = 65535
  cidr_blocks       = ["0.0.0.0/0"]
  ipv6_cidr_blocks  = ["::/0"]
  protocol          = "-1"
  description       = "Allow egress to anywhere"
}

resource "aws_alb" "GccExplorerApp" {
  idle_timeout    = 60
  internal        = false
  name            = "GccExplorerApp"
  security_groups = [
    aws_security_group.CompilerExplorerAlb.id
  ]
  subnets         = var.subnet_ids

  enable_deletion_protection = false

  access_logs {
    bucket  = var.log_bucket
    prefix  = var.log_prefix
    enabled = true
  }
}


resource "aws_autoscaling_group" "asg" {
  for_each = var.extra_environments
  lifecycle {
    create_before_destroy = true
  }

  default_cooldown          = local.cooldown
  health_check_grace_period = local.grace_period
  health_check_type         = "ELB"
  launch_template {
    id      = each.value.launch_configuration
    version = "$Latest"
  }

  max_size            = 4
  min_size            = 0
  name                = "spot-${each.key}"
  vpc_zone_identifier = var.subnet_ids

  target_group_arns = [aws_alb_target_group.ce[each.key].arn]
}
