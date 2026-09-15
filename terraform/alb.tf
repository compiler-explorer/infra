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

resource "aws_alb" "InternalServices" {
  idle_timeout = 60
  internal     = false
  name         = "InternalServices"
  security_groups = [
    aws_security_group.InternalServicesAlb.id
  ]
  subnets = local.all_subnet_ids

  enable_deletion_protection = false

  access_logs {
    bucket  = aws_s3_bucket.compiler-explorer-logs.bucket
    prefix  = "elb-internal"
    enabled = true
  }
}

# Only CloudFront should reach this ALB, but it is internet-facing with an open security group,
# so anything can address it directly and anyone's CloudFront distribution can use it as an
# origin. CloudFront stamps a secret header on every origin request (see cloudfront.tf); every
# forwarding rule below requires it and whatever is left over gets a fixed 403. This is the
# pattern from
# https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/restrict-access-to-load-balancer.html
# and it is what lets the app trust exactly two X-Forwarded-For hops (CloudFront, then the ALB).
#
# The value is kept in SSM so it can be inspected and so the ce-router killswitch can add the
# condition to the rules it creates. To rotate: terraform apply -replace=random_password.cloudfront_origin_secret
resource "random_password" "cloudfront_origin_secret" {
  length = 32
  # ALB header conditions treat * and ? as wildcards, and values are compared case-insensitively.
  special = false
}

resource "aws_ssm_parameter" "cloudfront_origin_secret" {
  name        = "/compiler-explorer/cloudfrontOriginSecret"
  description = "Value of the ${local.cloudfront_origin_header_name} header CloudFront sends to the GccExplorerApp ALB"
  type        = "SecureString"
  value       = random_password.cloudfront_origin_secret.result
}

locals {
  cloudfront_origin_header_name = "X-CE-Origin-Verify"
}

# Every distribution must be sending the header before any rule starts requiring it, otherwise
# real traffic gets refused mid-apply. The distributions wait for their own deployment to finish,
# so anything that depends on this is sequenced after them.
resource "terraform_data" "cloudfront_sends_origin_secret" {
  depends_on = [
    aws_cloudfront_distribution.ce-godbolt-org,
    aws_cloudfront_distribution.compiler-explorer-com,
    aws_cloudfront_distribution.godbo-lt,
  ]
}

# Nothing talks to the ALB over plain HTTP: CloudFront's origin protocol is https-only and the
# security group only admits CE nodes on this port (an hour of access logs showed no port-80
# requests at all). It used to forward to prod, so refuse instead of leaving a side door.
resource "aws_alb_listener" "compiler-explorer-alb-listen-http" {
  default_action {
    type = "fixed-response"
    fixed_response {
      content_type = "text/plain"
      message_body = "Access denied"
      status_code  = "403"
    }
  }

  load_balancer_arn = aws_alb.GccExplorerApp.arn
  port              = 80
  protocol          = "HTTP"
}

# Fails closed: a request that matched no forwarding rule did not carry the CloudFront origin
# header. Prod is served by compiler-explorer-alb-listen-https-prod, which blue-green
# deployments switch; nothing modifies this default action any more.
resource "aws_alb_listener" "compiler-explorer-alb-listen-https" {
  default_action {
    type = "fixed-response"
    fixed_response {
      content_type = "text/plain"
      message_body = "Access denied"
      status_code  = "403"
    }
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
  condition {
    http_header {
      http_header_name = local.cloudfront_origin_header_name
      values           = [random_password.cloudfront_origin_secret.result]
    }
  }
  listener_arn = aws_alb_listener.compiler-explorer-alb-listen-https.arn
  depends_on   = [terraform_data.cloudfront_sends_origin_secret]
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
  condition {
    http_header {
      http_header_name = local.cloudfront_origin_header_name
      values           = [random_password.cloudfront_origin_secret.result]
    }
  }
  listener_arn = aws_alb_listener.compiler-explorer-alb-listen-https.arn
  depends_on   = [terraform_data.cloudfront_sends_origin_secret]
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
  condition {
    http_header {
      http_header_name = local.cloudfront_origin_header_name
      values           = [random_password.cloudfront_origin_secret.result]
    }
  }
  listener_arn = aws_alb_listener.compiler-explorer-alb-listen-https.arn
  depends_on   = [terraform_data.cloudfront_sends_origin_secret]
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
  condition {
    http_header {
      http_header_name = local.cloudfront_origin_header_name
      values           = [random_password.cloudfront_origin_secret.result]
    }
  }
  listener_arn = aws_alb_listener.compiler-explorer-alb-listen-https.arn
  depends_on   = [terraform_data.cloudfront_sends_origin_secret]
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
  condition {
    http_header {
      http_header_name = local.cloudfront_origin_header_name
      values           = [random_password.cloudfront_origin_secret.result]
    }
  }
  listener_arn = aws_alb_listener.compiler-explorer-alb-listen-https.arn
  depends_on   = [terraform_data.cloudfront_sends_origin_secret]
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
  condition {
    http_header {
      http_header_name = local.cloudfront_origin_header_name
      values           = [random_password.cloudfront_origin_secret.result]
    }
  }
  listener_arn = aws_alb_listener.compiler-explorer-alb-listen-https.arn
  depends_on   = [terraform_data.cloudfront_sends_origin_secret]
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
  condition {
    http_header {
      http_header_name = local.cloudfront_origin_header_name
      values           = [random_password.cloudfront_origin_secret.result]
    }
  }
  listener_arn = aws_alb_listener.compiler-explorer-alb-listen-https.arn
  depends_on   = [terraform_data.cloudfront_sends_origin_secret]
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
  condition {
    http_header {
      http_header_name = local.cloudfront_origin_header_name
      values           = [random_password.cloudfront_origin_secret.result]
    }
  }
  listener_arn = aws_alb_listener.compiler-explorer-alb-listen-https.arn
  depends_on   = [terraform_data.cloudfront_sends_origin_secret]
}

# Prod is the catch-all. It used to be the listener's default action, but a rule can carry the
# origin header condition and a default action cannot. Blue-green deployments switch its target
# group (bin/lib/blue_green_deploy.py), hence ignore_changes on the action.
resource "aws_alb_listener_rule" "compiler-explorer-alb-listen-https-prod" {
  lifecycle {
    ignore_changes = [action]
  }

  priority = 1000
  action {
    type             = "forward"
    target_group_arn = module.prod_blue_green.target_group_arns["blue"]
  }
  condition {
    path_pattern {
      values = ["/*"]
    }
  }
  condition {
    http_header {
      http_header_name = local.cloudfront_origin_header_name
      values           = [random_password.cloudfront_origin_secret.result]
    }
  }
  listener_arn = aws_alb_listener.compiler-explorer-alb-listen-https.arn
  depends_on   = [terraform_data.cloudfront_sends_origin_secret]
}

# Anything that reached this point did not carry the CloudFront origin header. Created after the
# prod rule so there is never a moment where prod traffic has nothing to match.
resource "aws_alb_listener_rule" "compiler-explorer-alb-listen-https-deny-unverified" {
  priority = 50000
  action {
    type = "fixed-response"
    fixed_response {
      content_type = "text/plain"
      message_body = "Access denied"
      status_code  = "403"
    }
  }
  condition {
    path_pattern {
      values = ["/*"]
    }
  }
  listener_arn = aws_alb_listener.compiler-explorer-alb-listen-https.arn
  depends_on   = [aws_alb_listener_rule.compiler-explorer-alb-listen-https-prod]
}

resource "aws_alb_listener" "ceconan-alb-listen-http" {
  default_action {
    type             = "forward"
    target_group_arn = aws_alb_target_group.conan.arn
  }

  load_balancer_arn = aws_alb.InternalServices.arn
  port              = 1080
  protocol          = "HTTP"
}

resource "aws_alb_listener" "ceconan-alb-listen-https" {
  default_action {
    type             = "forward"
    target_group_arn = aws_alb_target_group.conan.arn
  }
  load_balancer_arn = aws_alb.InternalServices.arn
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
  condition {
    http_header {
      http_header_name = local.cloudfront_origin_header_name
      values           = [random_password.cloudfront_origin_secret.result]
    }
  }
  listener_arn = aws_alb_listener.compiler-explorer-alb-listen-https.arn
  depends_on   = [terraform_data.cloudfront_sends_origin_secret]
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
  condition {
    http_header {
      http_header_name = local.cloudfront_origin_header_name
      values           = [random_password.cloudfront_origin_secret.result]
    }
  }
  listener_arn = aws_alb_listener.compiler-explorer-alb-listen-https.arn
  depends_on   = [terraform_data.cloudfront_sends_origin_secret]
}
