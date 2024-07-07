
resource "aws_apigatewayv2_api" "ce_pub_api" {
  name          = "ce-pub-api"
  description   = "Public API to host some lambdas"
  protocol_type = "HTTP"
  cors_configuration {
    allow_origins = [
      "https://*"
    ]
  }
}

resource "aws_cloudwatch_log_group" "ce_pub_api_log" {
  name = "/aws/api_gw/${aws_apigatewayv2_api.ce_pub_api.name}"

  retention_in_days = 7
}

resource "aws_apigatewayv2_stage" "ce_pub_api_stage_prod" {
  api_id = aws_apigatewayv2_api.ce_pub_api.id

  name        = "prod"
  auto_deploy = true

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.ce_pub_api_log.arn

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
  api_id = aws_apigatewayv2_api.ce_pub_api.id

  integration_uri    = aws_lambda_function.get_deployed_exe_version.invoke_arn
  integration_type   = "AWS_PROXY"
  integration_method = "POST"
}

resource "aws_apigatewayv2_route" "get_deployed_exe_version" {
  api_id = aws_apigatewayv2_api.ce_pub_api.id

  route_key = "GET /get_deployed_exe_version"
  target    = "integrations/${aws_apigatewayv2_integration.get_deployed_exe_version.id}"
}

/* custom domain name for the api */

resource "aws_apigatewayv2_domain_name" "api-compiler-explorer-custom-domain" {
  domain_name = "api.compiler-explorer.com"

  domain_name_configuration {
    certificate_arn = aws_acm_certificate.godbolt-org-et-al.arn
    endpoint_type   = "REGIONAL"
    security_policy = "TLS_1_2"
  }
}

resource "aws_apigatewayv2_api_mapping" "api-compiler-explorer-mapping" {
  api_id      = aws_apigatewayv2_api.ce_pub_api.id
  domain_name = aws_apigatewayv2_domain_name.api-compiler-explorer-custom-domain.id
  stage       = aws_apigatewayv2_stage.ce_pub_api_stage_prod.id
}
