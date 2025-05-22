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
  image_tag = "gh-24"
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
    }
  }
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
