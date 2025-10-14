resource "aws_alb" "GccExplorerApp" {
  idle_timeout = 60
  internal     = false
  name         = "GccExplorerApp"
  security_groups = [
    aws_security_group.CompilerExplorerAlb.id
  ]
  subnets = local.all_subnet_ids

  enable_deletion_protection = false

  access_logs {
    bucket  = aws_s3_bucket.compiler-explorer-logs.bucket
    prefix  = "elb"
    enabled = true
  }
}

resource "aws_alb_listener" "compiler-explorer-alb-listen-http" {
  lifecycle {
    # Ignore changes to the default_action since it's managed by blue-green deployment
    ignore_changes = [default_action]
  }

  default_action {
    type             = "forward"
    target_group_arn = module.prod_blue_green.target_group_arns["blue"]
  }

  load_balancer_arn = aws_alb.GccExplorerApp.arn
  port              = 80
  protocol          = "HTTP"
}

resource "aws_alb_listener" "compiler-explorer-alb-listen-https" {
  lifecycle {
    # Ignore changes to the default_action since it's managed by blue-green deployment
    ignore_changes = [default_action]
  }

  default_action {
    type             = "forward"
    target_group_arn = module.prod_blue_green.target_group_arns["blue"]
  }
  load_balancer_arn = aws_alb.GccExplorerApp.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-2015-05"
  certificate_arn   = data.aws_acm_certificate.godbolt-org-et-al.arn
}

resource "aws_alb_listener_rule" "compiler-explorer-alb-listen-https-beta" {
  lifecycle {
    # Ignore changes to the action since it's managed by blue-green deployment
    ignore_changes = [action]
  }

  priority = 101
  action {
    type = "forward"
    # This target group ARN is managed by blue-green deployment process
    # The initial value doesn't matter as it will be overridden
    target_group_arn = module.beta_blue_green.target_group_arns["blue"]
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
  lifecycle {
    # Ignore changes to the action since it's managed by blue-green deployment
    ignore_changes = [action]
  }

  priority = 111
  action {
    type = "forward"
    # This target group ARN is managed by blue-green deployment process
    # The initial value doesn't matter as it will be overridden
    target_group_arn = module.staging_blue_green.target_group_arns["blue"]
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

resource "aws_alb_listener_rule" "compiler-explorer-alb-listen-https-gpu" {
  lifecycle {
    # Ignore changes to the action since it's managed by blue-green deployment
    ignore_changes = [action]
  }

  priority = 121
  action {
    type = "forward"
    # This target group ARN is managed by blue-green deployment process
    # The initial value doesn't matter as it will be overridden
    target_group_arn = module.gpu_blue_green.target_group_arns["blue"]
  }
  condition {
    path_pattern {
      values = [
        "/gpu*"
      ]
    }
  }
  listener_arn = aws_alb_listener.compiler-explorer-alb-listen-https.arn
}

resource "aws_alb_listener_rule" "compiler-explorer-alb-listen-https-wintest" {
  lifecycle {
    # Ignore changes to the action since it's managed by blue-green deployment
    ignore_changes = [action]
  }

  priority = 151
  action {
    type = "forward"
    # This target group ARN is managed by blue-green deployment process
    # The initial value doesn't matter as it will be overridden
    target_group_arn = module.wintest_blue_green.target_group_arns["blue"]
  }
  condition {
    path_pattern {
      values = [
        "/wintest*"
      ]
    }
  }
  listener_arn = aws_alb_listener.compiler-explorer-alb-listen-https.arn
}

resource "aws_alb_listener_rule" "compiler-explorer-alb-listen-https-winstaging" {
  lifecycle {
    # Ignore changes to the action since it's managed by blue-green deployment
    ignore_changes = [action]
  }

  priority = 161
  action {
    type = "forward"
    # This target group ARN is managed by blue-green deployment process
    # The initial value doesn't matter as it will be overridden
    target_group_arn = module.winstaging_blue_green.target_group_arns["blue"]
  }
  condition {
    path_pattern {
      values = [
        "/winstaging*"
      ]
    }
  }
  listener_arn = aws_alb_listener.compiler-explorer-alb-listen-https.arn
}

resource "aws_alb_listener_rule" "compiler-explorer-alb-listen-https-winprod" {
  lifecycle {
    # Ignore changes to the action since it's managed by blue-green deployment
    ignore_changes = [action]
  }

  priority = 171
  action {
    type = "forward"
    # This target group ARN is managed by blue-green deployment process
    # The initial value doesn't matter as it will be overridden
    target_group_arn = module.winprod_blue_green.target_group_arns["blue"]
  }
  condition {
    path_pattern {
      values = [
        "/winprod*"
      ]
    }
  }
  listener_arn = aws_alb_listener.compiler-explorer-alb-listen-https.arn
}

resource "aws_alb_listener_rule" "compiler-explorer-alb-listen-https-aarch64prod" {
  lifecycle {
    # Ignore changes to the action since it's managed by blue-green deployment
    ignore_changes = [action]
  }

  priority = 181
  action {
    type = "forward"
    # This target group ARN is managed by blue-green deployment process
    # The initial value doesn't matter as it will be overridden
    target_group_arn = module.aarch64prod_blue_green.target_group_arns["blue"]
  }
  condition {
    path_pattern {
      values = [
        "/aarch64prod*"
      ]
    }
  }
  listener_arn = aws_alb_listener.compiler-explorer-alb-listen-https.arn
}

resource "aws_alb_listener_rule" "compiler-explorer-alb-listen-https-aarch64staging" {
  lifecycle {
    # Ignore changes to the action since it's managed by blue-green deployment
    ignore_changes = [action]
  }

  priority = 191
  action {
    type = "forward"
    # This target group ARN is managed by blue-green deployment process
    # The initial value doesn't matter as it will be overridden
    target_group_arn = module.aarch64staging_blue_green.target_group_arns["blue"]
  }
  condition {
    path_pattern {
      values = [
        "/aarch64staging*"
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

resource "aws_alb_target_group" "lambda" {
  name        = "AwsLambdaTargetGroup"
  target_type = "lambda"
}

resource "aws_alb_target_group_attachment" "lambda-stats-endpoint" {
  target_group_arn = aws_alb_target_group.lambda.arn
  target_id        = aws_lambda_function.stats.arn
  depends_on       = [aws_lambda_permission.from_alb]
}

resource "aws_alb_listener_rule" "compiler-explorer-alb-listen-https-lambda" {
  priority = 131
  action {
    type             = "forward"
    target_group_arn = aws_alb_target_group.lambda.arn
  }
  condition {
    host_header {
      values = ["lambda.compiler-explorer.com"]
    }
  }
  listener_arn = aws_alb_listener.compiler-explorer-alb-listen-https.arn
}

resource "aws_alb_listener_rule" "compiler-explorer-alb-listen-https-stats" {
  priority = 141
  action {
    type = "redirect"
    redirect {
      status_code = "HTTP_301"
      host        = "ce.grafana.net"
      path        = "/public-dashboards/326d9aa2606b4efea25f4458a4c3f065"
      query       = "orgId=0&refresh=1m"
    }
  }
  condition {
    host_header {
      values = ["stats.compiler-explorer.com"]
    }
  }
  listener_arn = aws_alb_listener.compiler-explorer-alb-listen-https.arn
}

# Status API ALB listener rule
resource "aws_alb_listener_rule" "compiler-explorer-alb-listen-https-status" {
  priority = 201
  action {
    type             = "forward"
    target_group_arn = aws_alb_target_group.lambda_status.arn
  }
  condition {
    path_pattern {
      values = [
        "/api/status"
      ]
    }
  }
  listener_arn = aws_alb_listener.compiler-explorer-alb-listen-https.arn
}
