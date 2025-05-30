data "aws_ssm_parameter" "anthropic_api_key" {
  name = "/ce/claude/api-key"
}

resource "aws_cloudwatch_log_group" "explain" {
  name              = "/aws/lambda/explain"
  retention_in_days = 14
}

resource "aws_ecr_repository" "explain" {
  name = "explain"
}

data "aws_ecr_image" "explain" {
  repository_name = aws_ecr_repository.explain.name
  image_tag = "gh-41"
}

resource "aws_lambda_function" "explain" {
  description   = "Explain compiler assembly output using Claude"
  package_type  = "Image"
  image_uri     = data.aws_ecr_image.explain.image_uri
  function_name = "explain"
  role          = aws_iam_role.iam_for_lambda.arn
  timeout       = 30
  memory_size   = 256

  depends_on = [aws_cloudwatch_log_group.explain]

  environment {
    variables = {
      ANTHROPIC_API_KEY = data.aws_ssm_parameter.anthropic_api_key.value
      ROOT_PATH = "/explain"
      METRICS_ENABLED = "true"
      CACHE_ENABLED = "true"
      CACHE_S3_BUCKET = aws_s3_bucket.claude-explain-cache-godbolt-org.bucket
      CACHE_S3_PREFIX = ""
      CACHE_S3_TTL = "2d"  # TTL is the client-side TTL
    }
  }
}

// Bucket configuration; set to make this whole thing easy to remove if we decide it's a bad idea.
resource "aws_s3_bucket" "claude-explain-cache-godbolt-org" {
  bucket = "claude-explain-cache.godbolt.org"
  tags = {
    S3-Bucket-Name = "claude-explain-cache.godbolt.org"
  }
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_ownership_controls" "claude-explain-cache-godbolt-org" {
  bucket = aws_s3_bucket.claude-explain-cache-godbolt-org.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_public_access_block" "claude-explain-cache-godbolt-org" {
  bucket = aws_s3_bucket.claude-explain-cache-godbolt-org.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "claude-explain-cache-godbolt-org" {
  bucket = aws_s3_bucket.claude-explain-cache-godbolt-org.id
  rule {
    id     = "Remove cached items"
    status = "Enabled"
    expiration {
      days = 3
    }
    noncurrent_version_expiration {
      noncurrent_days = 1
    }
    filter {
      prefix = ""
    }
  }
}

# IAM Policy for S3 Access
data "aws_iam_policy_document" "explain_s3_access" {
  statement {
    sid = "ExplainCacheAccess"
    actions = [
      "s3:GetObject",
      "s3:PutObject"
    ]
    resources = ["${aws_s3_bucket.claude-explain-cache-godbolt-org.arn}/*"]
  }
}

resource "aws_iam_policy" "explain_s3_access" {
  name        = "explain_lambda_s3_access"
  description = "Allow explain lambda to access explain-cache prefix in cache bucket"
  policy      = data.aws_iam_policy_document.explain_s3_access.json
}

resource "aws_iam_role_policy_attachment" "explain_s3_access" {
  role       = aws_iam_role.iam_for_lambda.name
  policy_arn = aws_iam_policy.explain_s3_access.arn
}

# API Gateway Integration
resource "aws_apigatewayv2_integration" "explain" {
  api_id = aws_apigatewayv2_api.ce_pub_api.id

  integration_uri    = aws_lambda_function.explain.invoke_arn
  integration_type   = "AWS_PROXY"
  integration_method = "POST"
}

# API Gateway Route
resource "aws_apigatewayv2_route" "explain-root" {
  api_id = aws_apigatewayv2_api.ce_pub_api.id

  route_key = "ANY /explain"
  target    = "integrations/${aws_apigatewayv2_integration.explain.id}"
}

resource "aws_apigatewayv2_route" "explain-sub" {
  api_id = aws_apigatewayv2_api.ce_pub_api.id

  route_key = "ANY /explain/{proxy+}"
  target    = "integrations/${aws_apigatewayv2_integration.explain.id}"
}

# Lambda Permission for API Gateway
resource "aws_lambda_permission" "explain_api" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.explain.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.ce_pub_api.execution_arn}/*/*"
}

# TODO lambda.compiler-explorer.com vs api.
