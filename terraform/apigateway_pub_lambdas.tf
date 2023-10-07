
resource "aws_apigatewayv2_api" "ce_pub_lambdas" {
    name = "ce-pub-lambdas"
    description = "Public API to host some lambdas"
    protocol_type = "HTTP"
}

resource "aws_cloudwatch_log_group" "api_ce_pub_lambdas_gw" {
  name = "/aws/api_gw/${aws_apigatewayv2_api.ce_pub_lambdas.name}"

  retention_in_days = 7
}

resource "aws_apigatewayv2_stage" "prod" {
  api_id = aws_apigatewayv2_api.ce_pub_lambdas.id

  name        = "prod"
  auto_deploy = true

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api_ce_pub_lambdas_gw.arn

    format = jsonencode({
      requestId               = "$context.requestId"
      sourceIp                = "$context.identity.sourceIp"
      requestTime             = "$context.requestTime"
      protocol                = "$context.protocol"
      httpMethod              = "$context.httpMethod"
      resourcePath            = "$context.resourcePath"
      routeKey                = "$context.routeKey"
      status                  = "$context.status"
      responseLength          = "$context.responseLength"
      integrationErrorMessage = "$context.integrationErrorMessage"
      }
    )
  }
}

resource "aws_apigatewayv2_integration" "get_deployed_exe_version" {
  api_id = aws_apigatewayv2_api.ce_pub_lambdas.id

  integration_uri    = aws_lambda_function.get_deployed_exe_version.invoke_arn
  integration_type   = "AWS_PROXY"
  integration_method = "POST"
}

resource "aws_apigatewayv2_route" "get_deployed_exe_version" {
  api_id = aws_apigatewayv2_api.ce_pub_lambdas.id

  route_key = "GET /get_deployed_exe_version"
  target    = "integrations/${aws_apigatewayv2_integration.get_deployed_exe_version.id}"
}
