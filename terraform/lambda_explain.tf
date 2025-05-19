# IAM Policy for Claude Explain Lambda to access SSM Parameter Store
data "aws_iam_policy_document" "aws_lambda_explain" {
  statement {
    sid       = "GetClaudeApiKey"
    actions   = ["ssm:GetParameter"]
    resources = ["arn:aws:ssm:${local.region}:${data.aws_caller_identity.current.account_id}:parameter/ce/claude/api-key"]
  }
}

resource "aws_iam_policy" "aws_lambda_explain" {
  name        = "aws_lambda_explain"
  description = "Lambda explain policy (SSM Parameter Store access)"
  policy      = data.aws_iam_policy_document.aws_lambda_explain.json
}

resource "aws_iam_role_policy_attachment" "aws_lambda_explain" {
  role       = aws_iam_role.iam_for_lambda.name
  policy_arn = aws_iam_policy.aws_lambda_explain.arn
}

resource "aws_cloudwatch_log_group" "explain" {
  name              = "/aws/lambda/explain"
  retention_in_days = 14
}

resource "aws_lambda_function" "explain" {
  description       = "Explain compiler assembly output using Claude"
  s3_bucket         = data.aws_s3_object.lambda_zip.bucket
  s3_key            = data.aws_s3_object.lambda_zip.key
  s3_object_version = data.aws_s3_object.lambda_zip.version_id
  source_code_hash  = chomp(data.aws_s3_object.lambda_zip_sha.body)
  function_name     = "explain"
  role              = aws_iam_role.iam_for_lambda.arn
  handler           = "explain.lambda_handler"
  timeout           = 30
  memory_size       = 256

  runtime = "python3.12"

  depends_on = [aws_cloudwatch_log_group.explain]
}

# API Gateway Integration
resource "aws_apigatewayv2_integration" "explain" {
  api_id = aws_apigatewayv2_api.ce_pub_api.id

  integration_uri    = aws_lambda_function.explain.invoke_arn
  integration_type   = "AWS_PROXY"
  integration_method = "POST"
}

# API Gateway Route
resource "aws_apigatewayv2_route" "explain" {
  api_id = aws_apigatewayv2_api.ce_pub_api.id

  route_key = "POST /explain"
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
