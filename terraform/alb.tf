// TODO move into main?
resource "aws_alb_listener" "ceconan-alb-listen-http" {
  default_action {
    type             = "forward"
    target_group_arn = aws_alb_target_group.conan.arn
  }

  load_balancer_arn = module.main.alb.arn
  port              = 1080
  protocol          = "HTTP"
}

resource "aws_alb_listener" "ceconan-alb-listen-https" {
  default_action {
    type             = "forward"
    target_group_arn = aws_alb_target_group.conan.arn
  }
  load_balancer_arn = module.main.alb.arn
  port              = 1443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-2015-05"
  certificate_arn   = data.aws_acm_certificate.godbolt-org-et-al.arn
}

// TODO move this into main?
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
  priority     = 3
  action {
    type             = "forward"
    target_group_arn = aws_alb_target_group.lambda.arn
  }
  condition {
    host_header {
      values = ["lambda.compiler-explorer.com"]
    }
  }
  listener_arn = module.main.https_listener.arn
}
