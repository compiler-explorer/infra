/*
    Lambda's events-onconnect, events-ondisconnect, events-sendmessage

    These lambdas use Lambda Managed Instances for:
    - Zero cold starts (eliminates cascade failure risk)
    - AZ redundancy (3 instances minimum across AZs)
    - 50% burst absorption without scaling delays
    - Multi-concurrency (better resource utilization)

    See docs/lambda-managed-instances-plan.md for details.
 */


/* ==================== Lambda Managed Instances Capacity Provider ==================== */

resource "aws_lambda_capacity_provider" "events_websocket" {
  name = "events-websocket"

  vpc_config {
    subnet_ids         = local.all_subnet_ids
    security_group_ids = [aws_security_group.CompilerExplorer.id]
  }

  permissions_config {
    capacity_provider_operator_role_arn = aws_iam_role.lambda_capacity_operator.arn
  }

  instance_requirements {
    architectures          = ["ARM64"]
    allowed_instance_types = ["c8g.medium", "c8g.large"]
  }

  # Note: scaling_mode defaults to AUTO, max_vcpu_count defaults to 400
  # Explicit scaling config not needed for our use case

  tags = {
    Site = "CompilerExplorer"
  }
}

/* IAM role for capacity provider to manage EC2 instances */

data "aws_iam_policy_document" "lambda_capacity_operator_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    effect  = "Allow"
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda_capacity_operator" {
  name               = "lambda-capacity-provider-operator"
  assume_role_policy = data.aws_iam_policy_document.lambda_capacity_operator_trust.json
}

resource "aws_iam_role_policy_attachment" "lambda_capacity_operator" {
  role       = aws_iam_role.lambda_capacity_operator.name
  policy_arn = "arn:aws:iam::aws:policy/AWSLambdaManagedEC2ResourceOperator"
}

/* ==================== Lambda Execution Role ==================== */

/* main role */

data "aws_iam_policy_document" "aws_lambda_events_trust_policy" {
  statement {
    actions = ["sts:AssumeRole"]
    effect  = "Allow"
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "iam_for_lambda_events" {
  name               = "iam_for_lambda_events"
  assume_role_policy = data.aws_iam_policy_document.aws_lambda_events_trust_policy.json
}

data "aws_iam_policy_document" "aws_lambda_events_connections" {
  statement {
    sid       = "ManageConnections"
    resources = ["arn:aws:execute-api:*:*:*"]
    actions = [
      "execute-api:ManageConnections"
    ]
  }
}

resource "aws_iam_policy" "aws_lambda_events_connections" {
  name        = "aws_lambda_events_connections"
  description = "Allow ManageConnections"
  policy      = data.aws_iam_policy_document.aws_lambda_events_connections.json
}

/* logging policy */

data "aws_iam_policy_document" "aws_lambda_events_logging" {
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

resource "aws_iam_policy" "lambda_events_logging" {
  name        = "aws_lambda_events_logging"
  description = "Allow logging"
  policy      = data.aws_iam_policy_document.aws_lambda_events_logging.json
}

/* read from dynamodb policy */

data "aws_iam_policy_document" "aws_dynamodb_events" {
  statement {
    sid = "Allow"
    resources = [
      aws_dynamodb_table.events-connections.arn,
      "${aws_dynamodb_table.events-connections.arn}/index/*"
    ]
    actions = ["dynamodb:*"]
  }
}

resource "aws_iam_policy" "events_rw" {
  name        = "aws_events_rw"
  description = "Allow reading/writing to events-connections table"
  policy      = data.aws_iam_policy_document.aws_dynamodb_events.json
}

/* role attachments */

resource "aws_iam_role_policy_attachment" "terraform_lambda_events_policy" {
  role       = aws_iam_role.iam_for_lambda_events.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy_attachment" "lambda_events_logs" {
  role       = aws_iam_role.iam_for_lambda_events.name
  policy_arn = aws_iam_policy.lambda_events_logging.arn
}

resource "aws_iam_role_policy_attachment" "events_rw_att" {
  role       = aws_iam_role.iam_for_lambda_events.name
  policy_arn = aws_iam_policy.events_rw.arn
}

resource "aws_iam_role_policy_attachment" "aws_lambda_events_connections" {
  role       = aws_iam_role.iam_for_lambda_events.name
  policy_arn = aws_iam_policy.aws_lambda_events_connections.arn
}

/* lambda's */

resource "aws_lambda_function" "events_onconnect" {
  description       = "Lambda to events websocket connect"
  s3_bucket         = data.aws_s3_object.events_lambda_zip.bucket
  s3_key            = data.aws_s3_object.events_lambda_zip.key
  s3_object_version = data.aws_s3_object.events_lambda_zip.version_id
  source_code_hash  = chomp(data.aws_s3_object.events_lambda_zip_sha.body)
  function_name     = "events-onconnect"
  role              = aws_iam_role.iam_for_lambda_events.arn
  handler           = "events-onconnect.handler"

  runtime       = "nodejs22.x"
  architectures = ["arm64"]

  publish = true

  capacity_provider_config {
    lambda_managed_instances_capacity_provider_config {
      capacity_provider_arn                     = aws_lambda_capacity_provider.events_websocket.arn
      per_execution_environment_max_concurrency = 100
    }
  }

  depends_on = [aws_cloudwatch_log_group.events_onconnect]
}

resource "aws_lambda_function" "events_ondisconnect" {
  description       = "Lambda to events websocket disconnect"
  s3_bucket         = data.aws_s3_object.events_lambda_zip.bucket
  s3_key            = data.aws_s3_object.events_lambda_zip.key
  s3_object_version = data.aws_s3_object.events_lambda_zip.version_id
  source_code_hash  = chomp(data.aws_s3_object.events_lambda_zip_sha.body)
  function_name     = "events-ondisconnect"
  role              = aws_iam_role.iam_for_lambda_events.arn
  handler           = "events-ondisconnect.handler"

  runtime       = "nodejs22.x"
  architectures = ["arm64"]

  publish = true

  capacity_provider_config {
    lambda_managed_instances_capacity_provider_config {
      capacity_provider_arn                     = aws_lambda_capacity_provider.events_websocket.arn
      per_execution_environment_max_concurrency = 100
    }
  }

  depends_on = [aws_cloudwatch_log_group.events_ondisconnect]
}

resource "aws_lambda_function" "events_sendmessage" {
  description       = "Lambda to events websocket sendmessage"
  s3_bucket         = data.aws_s3_object.events_lambda_zip.bucket
  s3_key            = data.aws_s3_object.events_lambda_zip.key
  s3_object_version = data.aws_s3_object.events_lambda_zip.version_id
  source_code_hash  = chomp(data.aws_s3_object.events_lambda_zip_sha.body)
  function_name     = "events-sendmessage"
  role              = aws_iam_role.iam_for_lambda_events.arn
  handler           = "events-sendmessage.handler"
  memory_size       = 512 # Increased for better CPU and reduced GC pressure
  timeout           = 30  # Explicit timeout for API Gateway Management API calls

  runtime       = "nodejs22.x"
  architectures = ["arm64"]

  publish = true

  capacity_provider_config {
    lambda_managed_instances_capacity_provider_config {
      capacity_provider_arn                     = aws_lambda_capacity_provider.events_websocket.arn
      per_execution_environment_max_concurrency = 200 # Higher for main traffic handler
    }
  }

  depends_on = [aws_cloudwatch_log_group.events_sendmessage]
}

resource "aws_cloudwatch_log_group" "events_onconnect" {
  name              = "/aws/lambda/events-onconnect"
  retention_in_days = 1 # Minimum retention for high-volume production logging
}

resource "aws_cloudwatch_log_group" "events_ondisconnect" {
  name              = "/aws/lambda/events-ondisconnect"
  retention_in_days = 1 # Minimum retention for high-volume production logging
}

resource "aws_cloudwatch_log_group" "events_sendmessage" {
  name              = "/aws/lambda/events-sendmessage"
  retention_in_days = 1 # Minimum retention for high-volume production logging
}

## S3 things for the code

data "aws_s3_object" "events_lambda_zip" {
  # Lambda zip is uploaded and rebuild by the Makefile: make upload-queue-lambda
  bucket = aws_s3_bucket.compiler-explorer.bucket
  key    = "lambdas/events-lambda-package.zip"
}

data "aws_s3_object" "events_lambda_zip_sha" {
  # Lambda zip's SHA256 is uploaded and rebuild by the Makefile: make upload-queue-lambda
  bucket = aws_s3_bucket.compiler-explorer.bucket
  key    = "lambdas/events-lambda-package.zip.sha256"
}

## API

resource "aws_lambda_permission" "events_onconnect" {
  statement_id  = "AllowExecutionFromAPIGateway"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.events_onconnect.arn
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.events_api.execution_arn}/*/*"
}

resource "aws_lambda_permission" "events_ondisconnect" {
  statement_id  = "AllowExecutionFromAPIGateway"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.events_ondisconnect.arn
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.events_api.execution_arn}/*/*"
}

resource "aws_lambda_permission" "events_sendmessage" {
  statement_id  = "AllowExecutionFromAPIGateway"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.events_sendmessage.arn
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.events_api.execution_arn}/*/*"
}

# Provisioned concurrency replaced by Lambda Managed Instances capacity provider.
# The capacity provider (events_websocket) provides:
# - Zero cold starts via pre-provisioned EC2 instances
# - Multi-concurrency (multiple requests per execution environment)
# - AZ redundancy (3 instances minimum)
#
# To revert to Provisioned Concurrency, uncomment below and remove
# capacity_provider_config blocks from the Lambda functions.
#
# resource "aws_lambda_provisioned_concurrency_config" "events_sendmessage" {
#   function_name                     = aws_lambda_function.events_sendmessage.function_name
#   provisioned_concurrent_executions = 5
#   qualifier                         = aws_lambda_function.events_sendmessage.version
# }
#
# resource "aws_lambda_provisioned_concurrency_config" "events_onconnect" {
#   function_name                     = aws_lambda_function.events_onconnect.function_name
#   provisioned_concurrent_executions = 1
#   qualifier                         = aws_lambda_function.events_onconnect.version
# }
#
# resource "aws_lambda_provisioned_concurrency_config" "events_ondisconnect" {
#   function_name                     = aws_lambda_function.events_ondisconnect.function_name
#   provisioned_concurrent_executions = 1
#   qualifier                         = aws_lambda_function.events_ondisconnect.version
# }
