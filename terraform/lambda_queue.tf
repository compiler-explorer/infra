/*
    Lambda's queue-onconnect, queue-ondisconnect, queue-sendmessage
 */


/* main role */

data "aws_iam_policy_document" "aws_lambda_queue_trust_policy" {
  statement {
    actions = ["sts:AssumeRole"]
    effect  = "Allow"
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "iam_for_lambda_queue" {
  name               = "iam_for_lambda_queue"
  assume_role_policy = data.aws_iam_policy_document.aws_lambda_queue_trust_policy.json
}

/* logging policy */

data "aws_iam_policy_document" "aws_lambda_queue_logging" {
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

resource "aws_iam_policy" "lambda_queue_logging" {
  name        = "aws_lambda_queue_logging"
  description = "Allow logging"
  policy      = data.aws_iam_policy_document.aws_lambda_queue_logging.json
}

/* read from dynamodb policy */

data "aws_iam_policy_document" "aws_dynamodb_queue" {
  statement {
    sid       = "Allow"
    resources = [aws_dynamodb_table.queue-connections.arn]
    actions   = ["dynamodb:*"]
  }
}

resource "aws_iam_policy" "queue_rw" {
  name        = "aws_queue_rw"
  description = "Allow reading/writing to queue-connections table"
  policy      = data.aws_iam_policy_document.aws_dynamodb_queue.json
}

/* role attachments */

resource "aws_iam_role_policy_attachment" "terraform_lambda_queue_policy" {
  role       = aws_iam_role.iam_for_lambda_queue.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy_attachment" "lambda_queue_logs" {
  role       = aws_iam_role.iam_for_lambda_queue.name
  policy_arn = aws_iam_policy.lambda_queue_logging.arn
}

resource "aws_iam_role_policy_attachment" "queue_rw_att" {
  role       = aws_iam_role.iam_for_lambda_queue.name
  policy_arn = aws_iam_policy.queue_rw.arn
}

/* lambda's */

resource "aws_lambda_function" "queue_onconnect" {
  description       = "Lambda to queue websocket connect"
  s3_bucket         = data.aws_s3_object.queue_lambda_zip.bucket
  s3_key            = data.aws_s3_object.queue_lambda_zip.key
  s3_object_version = data.aws_s3_object.queue_lambda_zip.version_id
  source_code_hash  = chomp(data.aws_s3_object.queue_lambda_zip_sha.body)
  function_name     = "queue-onconnect"
  role              = aws_iam_role.iam_for_lambda_queue.arn
  handler           = "queue-onconnect.handler"

  runtime = "nodejs20.x"

  depends_on = [aws_cloudwatch_log_group.queue]
}

resource "aws_lambda_function" "queue_ondisconnect" {
  description       = "Lambda to queue websocket disconnect"
  s3_bucket         = data.aws_s3_object.queue_lambda_zip.bucket
  s3_key            = data.aws_s3_object.queue_lambda_zip.key
  s3_object_version = data.aws_s3_object.queue_lambda_zip.version_id
  source_code_hash  = chomp(data.aws_s3_object.queue_lambda_zip_sha.body)
  function_name     = "queue-ondisconnect"
  role              = aws_iam_role.iam_for_lambda_queue.arn
  handler           = "queue-ondisconnect.handler"

  runtime = "nodejs20.x"

  depends_on = [aws_cloudwatch_log_group.queue]
}

resource "aws_lambda_function" "queue_sendmessage" {
  description       = "Lambda to queue websocket sendmessage"
  s3_bucket         = data.aws_s3_object.queue_lambda_zip.bucket
  s3_key            = data.aws_s3_object.queue_lambda_zip.key
  s3_object_version = data.aws_s3_object.queue_lambda_zip.version_id
  source_code_hash  = chomp(data.aws_s3_object.queue_lambda_zip_sha.body)
  function_name     = "queue-sendmessage"
  role              = aws_iam_role.iam_for_lambda_queue.arn
  handler           = "queue-sendmessage.handler"

  runtime = "nodejs20.x"

  depends_on = [aws_cloudwatch_log_group.queue]
}

resource "aws_cloudwatch_log_group" "queue" {
  name              = "/aws/lambda/queue"
  retention_in_days = 7
}

# resource "aws_lambda_permission" "with_api_gateway" {
#   statement_id  = "AllowExecutionFromAPIGateway"
#   action        = "lambda:InvokeFunction"
#   function_name = aws_lambda_function.get_deployed_exe_version.arn
#   principal     = "apigateway.amazonaws.com"
#   source_arn    = "${aws_apigatewayv2_api.ce_pub_api.execution_arn}/*/*"
# }
