/*
    Lambda get_deployed_exe_version
    Rights to log and read from dynamodb tables nightly-version and nightly-exe
    API Gateway can execute the lambda
 */


/* main role */

data "aws_iam_policy_document" "aws_lambda_nightlyversion_trust_policy" {
  statement {
    actions = ["sts:AssumeRole"]
    effect  = "Allow"
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "iam_for_lambda_nightlyversion" {
  name               = "iam_for_lambda_nightlyversion"
  assume_role_policy = data.aws_iam_policy_document.aws_lambda_nightlyversion_trust_policy.json
}

/* logging policy */

data "aws_iam_policy_document" "aws_lambda_nightlyversion_logging" {
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

resource "aws_iam_policy" "lambda_nightlyversion_logging" {
  name        = "aws_lambda_nightlyversion_logging"
  description = "Allow logging"
  policy      = data.aws_iam_policy_document.aws_lambda_nightlyversion_logging.json
}

/* read from dynamodb policy */

data "aws_iam_policy_document" "aws_dynamodb_nightlyversion" {
  statement {
    sid       = "Allow"
    resources = [aws_dynamodb_table.nightly-version.arn, aws_dynamodb_table.nightly-exe.arn]
    actions   = ["dynamodb:GetItem"]
  }
}

resource "aws_iam_policy" "nightlyversion_readonly" {
  name        = "aws_nightlyversion_readonly"
  description = "Allow reading from nightly-version and nightly-exe tables"
  policy      = data.aws_iam_policy_document.aws_dynamodb_nightlyversion.json
}

/* role attachments */

resource "aws_iam_role_policy_attachment" "terraform_lambda_nightlyversion_policy" {
  role       = aws_iam_role.iam_for_lambda_nightlyversion.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy_attachment" "lambda_nightlyversion_logs" {
  role       = aws_iam_role.iam_for_lambda_nightlyversion.name
  policy_arn = aws_iam_policy.lambda_nightlyversion_logging.arn
}

resource "aws_iam_role_policy_attachment" "nightlyversion_ro_att" {
  role       = aws_iam_role.iam_for_lambda_nightlyversion.name
  policy_arn = aws_iam_policy.nightlyversion_readonly.arn
}

/* lambda */

resource "aws_lambda_function" "get_deployed_exe_version" {
  description       = "Lambda to get the current version number for a given trunk compiler"
  s3_bucket         = data.aws_s3_object.lambda_zip.bucket
  s3_key            = data.aws_s3_object.lambda_zip.key
  s3_object_version = data.aws_s3_object.lambda_zip.version_id
  source_code_hash  = chomp(data.aws_s3_object.lambda_zip_sha.body)
  function_name     = "get_deployed_exe_version"
  role              = aws_iam_role.iam_for_lambda_nightlyversion.arn
  handler           = "get_deployed_exe_version.lambda_handler"

  runtime = "python3.8"

  depends_on = [aws_cloudwatch_log_group.get_deployed_exe_version]
}

resource "aws_cloudwatch_log_group" "get_deployed_exe_version" {
  name              = "/aws/lambda/get_deployed_exe_version"
  retention_in_days = 7
}

resource "aws_lambda_permission" "with_api_gateway" {
  statement_id  = "AllowExecutionFromAPIGateway"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.get_deployed_exe_version.arn
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.ce_pub_api.execution_arn}/*/*"
}
