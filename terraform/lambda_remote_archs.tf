
/* main role */

data "aws_iam_policy_document" "aws_lambda_remotearchs_trust_policy" {
  statement {
    actions = ["sts:AssumeRole"]
    effect  = "Allow"
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "iam_for_lambda_remotearchs" {
  name               = "iam_for_lambda_remotearchs"
  assume_role_policy = data.aws_iam_policy_document.aws_lambda_remotearchs_trust_policy.json
}

/* logging policy */

data "aws_iam_policy_document" "aws_lambda_remotearchs_logging" {
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

resource "aws_iam_policy" "lambda_remotearchs_logging" {
  name        = "aws_lambda_remotearchs_logging"
  description = "Allow logging"
  policy      = data.aws_iam_policy_document.aws_lambda_remotearchs_logging.json
}

/* read from dynamodb policy */

data "aws_iam_policy_document" "aws_dynamodb_remotearchs" {
  statement {
    sid       = "Allow"
    resources = [aws_dynamodb_table.prod-remote-exec-archs.arn, aws_dynamodb_table.staging-remote-exec-archs.arn]
    actions   = ["dynamodb:Scan"]
  }
}

resource "aws_iam_policy" "remotearchs_readonly" {
  name        = "aws_remotearchs_readonly"
  description = "Allow reading from remote-archs table"
  policy      = data.aws_iam_policy_document.aws_dynamodb_remotearchs.json
}

/* role attachments */

resource "aws_iam_role_policy_attachment" "terraform_lambda_remotearchs_policy" {
  role       = aws_iam_role.iam_for_lambda_remotearchs.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy_attachment" "lambda_remotearchs_logs" {
  role       = aws_iam_role.iam_for_lambda_remotearchs.name
  policy_arn = aws_iam_policy.lambda_remotearchs_logging.arn
}

resource "aws_iam_role_policy_attachment" "remotearchs_ro_att" {
  role       = aws_iam_role.iam_for_lambda_remotearchs.name
  policy_arn = aws_iam_policy.remotearchs_readonly.arn
}

/* part of the "lambda" package (python) */

resource "aws_lambda_function" "get_remote_execution_archs" {
  description       = "Lambda to get active architectures that allow remote execution"
  s3_bucket         = data.aws_s3_object.lambda_zip.bucket
  s3_key            = data.aws_s3_object.lambda_zip.key
  s3_object_version = data.aws_s3_object.lambda_zip.version_id
  source_code_hash  = chomp(data.aws_s3_object.lambda_zip_sha.body)
  function_name     = "get_remote_execution_archs"
  role              = aws_iam_role.iam_for_lambda_remotearchs.arn
  handler           = "get_remote_execution_archs.lambda_handler"

  runtime = "python3.12"

  depends_on = [aws_cloudwatch_log_group.get_remote_execution_archs]
}

resource "aws_cloudwatch_log_group" "get_remote_execution_archs" {
  name              = "/aws/lambda/get_remote_execution_archs"
  retention_in_days = 7
}

resource "aws_lambda_permission" "remote_args_with_api_gateway" {
  statement_id  = "AllowExecutionFromAPIGateway"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.get_remote_execution_archs.arn
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.ce_pub_api.execution_arn}/*/*"
}
