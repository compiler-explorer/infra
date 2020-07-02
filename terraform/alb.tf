resource "aws_alb" "GccExplorerApp" {
  idle_timeout    = 60
  internal        = false
  name            = "GccExplorerApp"
  security_groups = [
    aws_security_group.CompilerExplorerAlb.id
  ]
  subnets         = [
    aws_subnet.ce-1a.id,
    aws_subnet.ce-1b.id,
    aws_subnet.ce-1c.id,
    aws_subnet.ce-1d.id,
    aws_subnet.ce-1e.id,
    aws_subnet.ce-1f.id
  ]

  enable_deletion_protection = false

  access_logs {
    bucket  = aws_s3_bucket.compiler-explorer-logs.bucket
    prefix  = "elb"
    enabled = true
  }

  tags = {
    Site = "CompilerExplorer"
  }
}

resource "aws_alb_listener" "compiler-explorer-alb-listen-http" {
  default_action {
    type             = "forward"
    target_group_arn = aws_alb_target_group.prod.arn
  }

  load_balancer_arn = aws_alb.GccExplorerApp.arn
  port              = 80
  protocol          = "HTTP"
}

resource "aws_alb_listener_rule" "compiler-explorer-alb-listen-http-beta" {
  priority     = 1
  action {
    type             = "forward"
    target_group_arn = aws_alb_target_group.beta.arn
  }
  condition {
    path_pattern {
      values = ["/beta*"]
    }
  }
  listener_arn = aws_alb_listener.compiler-explorer-alb-listen-http.arn
}

resource "aws_alb_listener_rule" "compiler-explorer-alb-listen-http-staging" {
  priority     = 2
  action {
    type             = "forward"
    target_group_arn = aws_alb_target_group.staging.arn
  }
  condition {
    path_pattern {
      values = [
        "/staging*"
      ]
    }
  }
  listener_arn = aws_alb_listener.compiler-explorer-alb-listen-http.arn
}

resource "aws_alb_listener" "compiler-explorer-alb-listen-https" {
  default_action {
    type             = "forward"
    target_group_arn = aws_alb_target_group.prod.arn
  }
  load_balancer_arn = aws_alb.GccExplorerApp.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-2015-05"
  certificate_arn   = data.aws_acm_certificate.godbolt-org-et-al.arn
}

resource "aws_alb_listener_rule" "compiler-explorer-alb-listen-https-beta" {
  priority     = 1
  action {
    type             = "forward"
    target_group_arn = aws_alb_target_group.beta.arn
  }
  condition {
    path_pattern {
      values = [
        "/beta*"
      ]
    }
  }
  listener_arn = aws_alb_listener.compiler-explorer-alb-listen-https.arn
}

resource "aws_alb_listener_rule" "compiler-explorer-alb-listen-https-staging" {
  priority     = 2
  action {
    type             = "forward"
    target_group_arn = aws_alb_target_group.staging.arn
  }
  condition {
    path_pattern {
      values = [
        "/staging*"
      ]
    }
  }
  listener_arn = aws_alb_listener.compiler-explorer-alb-listen-https.arn
}

resource "aws_alb_listener" "ceconan-alb-listen-http" {
  default_action {
    type             = "forward"
    target_group_arn = aws_alb_target_group.conan.arn
  }

  load_balancer_arn = aws_alb.GccExplorerApp.arn
  port              = 1080
  protocol          = "HTTP"
}

resource "aws_alb_listener" "ceconan-alb-listen-https" {
  default_action {
    type             = "forward"
    target_group_arn = aws_alb_target_group.conan.arn
  }
  load_balancer_arn = aws_alb.GccExplorerApp.arn
  port              = 1443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-2015-05"
  certificate_arn   = data.aws_acm_certificate.godbolt-org-et-al.arn
}
