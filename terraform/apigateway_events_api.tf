
resource "aws_apigatewayv2_api" "events_api" {
  name          = "events-api"
  description   = "Websocket for the events API"
  protocol_type = "WEBSOCKET"

  route_selection_expression = "$request.body.action"
}

resource "aws_apigatewayv2_integration" "events_api_message" {
  api_id             = aws_apigatewayv2_api.events_api.id
  integration_type   = "AWS_PROXY"
  integration_uri    = aws_lambda_function.events_sendmessage.invoke_arn
  integration_method = "POST"
}

resource "aws_apigatewayv2_integration" "events_api_connect" {
  api_id             = aws_apigatewayv2_api.events_api.id
  integration_type   = "AWS_PROXY"
  integration_uri    = aws_lambda_function.events_onconnect.invoke_arn
  integration_method = "POST"
}

resource "aws_apigatewayv2_integration" "events_api_disconnect" {
  api_id             = aws_apigatewayv2_api.events_api.id
  integration_type   = "AWS_PROXY"
  integration_uri    = aws_lambda_function.events_ondisconnect.invoke_arn
  integration_method = "POST"
}

resource "aws_apigatewayv2_route" "events_api_message" {
  api_id    = aws_apigatewayv2_api.events_api.id
  route_key = "$default"
  target    = "integrations/${aws_apigatewayv2_integration.events_api_message.id}"
}

resource "aws_apigatewayv2_route" "events_api_connect" {
  api_id    = aws_apigatewayv2_api.events_api.id
  route_key = "$connect"
  target    = "integrations/${aws_apigatewayv2_integration.events_api_connect.id}"
}

resource "aws_apigatewayv2_route" "events_api_disconnect" {
  api_id    = aws_apigatewayv2_api.events_api.id
  route_key = "$disconnect"
  target    = "integrations/${aws_apigatewayv2_integration.events_api_disconnect.id}"
}

resource "aws_cloudwatch_log_group" "events_api_log" {
  name = "/aws/api_gw/${aws_apigatewayv2_api.events_api.name}"

  retention_in_days = 7
}

resource "aws_apigatewayv2_stage" "events_api_stage_prod" {
  api_id = aws_apigatewayv2_api.events_api.id

  name        = "prod"
  auto_deploy = true

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.events_api_log.arn

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

resource "aws_apigatewayv2_stage" "events_api_stage_staging" {
  api_id = aws_apigatewayv2_api.events_api.id

  name        = "staging"
  auto_deploy = true

  default_route_settings {
    logging_level = "INFO"
    detailed_metrics_enabled = true
    data_trace_enabled = true
    throttling_rate_limit = 1000
    throttling_burst_limit = 1000
  }

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.events_api_log.arn

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

/* logging policy */

data "aws_iam_policy_document" "events_api_logging" {
  statement {
    sid       = "AllowLogging"
    resources = ["arn:aws:logs:*:*:*"]
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents"
    ]
  }
}

resource "aws_iam_policy" "events_api_logging" {
  name        = "events_api_logging"
  description = "Allow logging"
  policy      = data.aws_iam_policy_document.events_api_logging.json
}

/* custom domain name for the api */
/* 'Currently, WebSocket APIs cannot be mixed with REST APIs or HTTP APIs on the same domain name.' */

resource "aws_apigatewayv2_domain_name" "events-api-compiler-explorer-custom-domain" {
  domain_name = "events.compiler-explorer.com"

  domain_name_configuration {
    certificate_arn = aws_acm_certificate.godbolt-org-et-al.arn
    endpoint_type   = "REGIONAL"
    security_policy = "TLS_1_2"
  }
}

resource "aws_apigatewayv2_api_mapping" "events-api-compiler-explorer-mapping-prod" {
  api_id          = aws_apigatewayv2_api.events_api.id
  domain_name     = aws_apigatewayv2_domain_name.events-api-compiler-explorer-custom-domain.id
  stage           = aws_apigatewayv2_stage.events_api_stage_prod.id
  api_mapping_key = "prod"
}

resource "aws_apigatewayv2_api_mapping" "events-api-compiler-explorer-mapping-staging" {
  api_id          = aws_apigatewayv2_api.events_api.id
  domain_name     = aws_apigatewayv2_domain_name.events-api-compiler-explorer-custom-domain.id
  stage           = aws_apigatewayv2_stage.events_api_stage_staging.id
  api_mapping_key = "staging"
}
