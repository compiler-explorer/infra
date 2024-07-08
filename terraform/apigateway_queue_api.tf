
resource "aws_apigatewayv2_api" "queue_api" {
  name          = "queue-api"
  description   = "Websocket for the Queue API"
  protocol_type = "WEBSOCKET"

  route_selection_expression = "$request.body.action"
}

resource "aws_apigatewayv2_integration" "queue_api_message" {
  api_id             = aws_apigatewayv2_api.queue_api.id
  integration_type   = "AWS_PROXY"
  integration_uri    = aws_lambda_function.queue_sendmessage.invoke_arn
  integration_method = "POST"
}

resource "aws_apigatewayv2_integration" "queue_api_connect" {
  api_id             = aws_apigatewayv2_api.queue_api.id
  integration_type   = "AWS_PROXY"
  integration_uri    = aws_lambda_function.queue_onconnect.invoke_arn
  integration_method = "POST"
}

resource "aws_apigatewayv2_integration" "queue_api_disconnect" {
  api_id             = aws_apigatewayv2_api.queue_api.id
  integration_type   = "AWS_PROXY"
  integration_uri    = aws_lambda_function.queue_ondisconnect.invoke_arn
  integration_method = "POST"
}

resource "aws_apigatewayv2_route" "queue_api_message" {
  api_id    = aws_apigatewayv2_api.queue_api.id
  route_key = "$default"
  target    = "integrations/${aws_apigatewayv2_integration.queue_api_message.id}"
}

resource "aws_apigatewayv2_route" "queue_api_connect" {
  api_id    = aws_apigatewayv2_api.queue_api.id
  route_key = "$connect"
  target    = "integrations/${aws_apigatewayv2_integration.queue_api_connect.id}"
}

resource "aws_apigatewayv2_route" "queue_api_disconnect" {
  api_id    = aws_apigatewayv2_api.queue_api.id
  route_key = "$disconnect"
  target    = "integrations/${aws_apigatewayv2_integration.queue_api_disconnect.id}"
}

resource "aws_cloudwatch_log_group" "queue_api_log" {
  name = "/aws/api_gw/${aws_apigatewayv2_api.queue_api.name}"

  retention_in_days = 7
}

resource "aws_apigatewayv2_stage" "queue_api_stage_prod" {
  api_id = aws_apigatewayv2_api.queue_api.id

  name        = "prod"
  auto_deploy = true

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.queue_api_log.arn

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

data "aws_iam_policy_document" "queue_api_logging" {
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

resource "aws_iam_policy" "queue_api_logging" {
  name        = "queue_api_logging"
  description = "Allow logging"
  policy      = data.aws_iam_policy_document.queue_api_logging.json
}

/* custom domain name for the api */

resource "aws_apigatewayv2_domain_name" "queue-api-compiler-explorer-custom-domain" {
  domain_name = "queue.compiler-explorer.com"

  domain_name_configuration {
    certificate_arn = aws_acm_certificate.godbolt-org-et-al.arn
    endpoint_type   = "REGIONAL"
    security_policy = "TLS_1_2"
  }
}

resource "aws_apigatewayv2_api_mapping" "queue-api-compiler-explorer-mapping" {
  api_id      = aws_apigatewayv2_api.queue_api.id
  domain_name = aws_apigatewayv2_domain_name.queue-api-compiler-explorer-custom-domain.id
  stage       = aws_apigatewayv2_stage.queue_api_stage_prod.id
}
