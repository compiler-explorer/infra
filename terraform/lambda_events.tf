/*
    Lambda's events-onconnect, events-ondisconnect, events-sendmessage
 */


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
    sid = "ManageConnections"
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
    sid       = "Allow"
    resources = [aws_dynamodb_table.events-connections.arn]
    actions   = ["dynamodb:*"]
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

  runtime       = "nodejs20.x"
  architectures = ["arm64"]

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

  runtime       = "nodejs20.x"
  architectures = ["arm64"]

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

  runtime       = "nodejs20.x"
  architectures = ["arm64"]

  depends_on = [aws_cloudwatch_log_group.events_sendmessage]
}

resource "aws_cloudwatch_log_group" "events_onconnect" {
  name              = "/aws/lambda/events_onconnect"
  retention_in_days = 7
}

resource "aws_cloudwatch_log_group" "events_ondisconnect" {
  name              = "/aws/lambda/events_ondisconnect"
  retention_in_days = 7
}

resource "aws_cloudwatch_log_group" "events_sendmessage" {
  name              = "/aws/lambda/events_sendmessage"
  retention_in_days = 7
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
