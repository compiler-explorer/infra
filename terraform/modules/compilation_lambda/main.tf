# Main configuration for compilation Lambda module

# SQS FIFO Queue for compilation requests
resource "aws_sqs_queue" "compilation_queue" {
  name                        = "${var.environment}-compilation-queue.fifo"
  fifo_queue                  = true
  content_based_deduplication = false
  message_retention_seconds   = var.sqs_message_retention_seconds
  visibility_timeout_seconds  = var.sqs_visibility_timeout_seconds

  tags = merge({
    Environment = var.environment
    Purpose     = "compilation-requests"
  }, var.tags)
}

# Get compilation lambda package from S3
data "aws_s3_object" "compilation_lambda_zip" {
  bucket = var.s3_bucket
  key    = var.lambda_package_key
}

data "aws_s3_object" "compilation_lambda_zip_sha" {
  bucket = var.s3_bucket
  key    = var.lambda_package_sha_key
}

# CloudWatch log group for Lambda
resource "aws_cloudwatch_log_group" "compilation" {
  name              = "/aws/lambda/compilation-${var.environment}"
  retention_in_days = var.cloudwatch_log_retention_days

  tags = merge({
    Environment = var.environment
    Purpose     = "compilation-logs"
  }, var.tags)
}

# Lambda function
resource "aws_lambda_function" "compilation" {
  description       = "Handle compilation requests for ${var.environment} environment"
  s3_bucket         = data.aws_s3_object.compilation_lambda_zip.bucket
  s3_key            = data.aws_s3_object.compilation_lambda_zip.key
  s3_object_version = data.aws_s3_object.compilation_lambda_zip.version_id
  source_code_hash  = chomp(data.aws_s3_object.compilation_lambda_zip_sha.body)
  function_name     = "compilation-${var.environment}"
  role              = var.iam_role_arn
  handler           = "index.handler"
  timeout           = var.lambda_timeout

  runtime = "nodejs22.x"

  architectures = ["arm64"]

  environment {
    variables = {
      SQS_QUEUE_URL    = aws_sqs_queue.compilation_queue.id
      WEBSOCKET_URL    = var.websocket_url
      RETRY_COUNT      = var.lambda_retry_count
      TIMEOUT_SECONDS  = var.lambda_timeout_seconds
      ENVIRONMENT_NAME = var.environment
    }
  }

  depends_on = [aws_cloudwatch_log_group.compilation]

  publish = true # Required for provisioned concurrency

  tags = merge({
    Environment = var.environment
    Purpose     = "compilation"
  }, var.tags)
}

# ALB Target Group for Lambda function
resource "aws_alb_target_group" "compilation_lambda" {
  name        = "compilation-lambda-${var.environment}"
  target_type = "lambda"

  # Health checks are not applicable for Lambda target groups
  # Lambda functions are automatically considered healthy

  tags = merge({
    Environment = var.environment
    Purpose     = "compilation-lambda"
  }, var.tags)
}

# ALB Target Group Attachment for Lambda function
resource "aws_alb_target_group_attachment" "compilation_lambda" {
  target_group_arn = aws_alb_target_group.compilation_lambda.arn
  target_id        = aws_lambda_function.compilation.arn

  depends_on = [aws_lambda_permission.compilation_alb]
}

# Lambda permission for ALB to invoke function
resource "aws_lambda_permission" "compilation_alb" {
  statement_id  = "AllowExecutionFromALB"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.compilation.arn
  principal     = "elasticloadbalancing.amazonaws.com"
  source_arn    = aws_alb_target_group.compilation_lambda.arn
}

# ALB Listener Rule (conditional based on enable_alb_listener)
resource "aws_alb_listener_rule" "compilation" {
  count = var.enable_alb_listener ? 1 : 0

  priority = var.alb_priority

  action {
    type             = "forward"
    target_group_arn = aws_alb_target_group.compilation_lambda.arn
  }

  condition {
    path_pattern {
      values = var.alb_path_patterns
    }
  }

  listener_arn = var.alb_listener_arn

  tags = merge({
    Environment = var.environment
    Purpose     = "compilation-routing"
  }, var.tags)
}

# Provisioned concurrency to keep at least 1 instance warm
resource "aws_lambda_provisioned_concurrency_config" "compilation" {
  function_name                     = aws_lambda_function.compilation.function_name
  provisioned_concurrent_executions = 1
  qualifier                         = aws_lambda_function.compilation.version
}
