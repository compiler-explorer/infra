data "aws_iam_policy_document" "aws_lambda_trust_policy" {
  statement {
    actions = ["sts:AssumeRole"]
    effect  = "Allow"
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}
resource "aws_iam_role" "iam_for_lambda" {
  name               = "iam_for_lambda"
  assume_role_policy = data.aws_iam_policy_document.aws_lambda_trust_policy.json
}


resource "aws_iam_role_policy_attachment" "terraform_lambda_policy" {
  role       = aws_iam_role.iam_for_lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_ssm_parameter" "discord_webhook_url" {
  name = "/admin/discord_webhook_url"
}

resource "aws_sns_topic_subscription" "sns_to_lambda" {
  topic_arn = data.aws_sns_topic.alert.arn
  protocol  = "lambda"
  endpoint  = aws_lambda_function.cloudwatch_to_discord.arn
}

data "aws_s3_bucket_object" "lambda_zip" {
  # Lambda zip is uploaded and rebuild by the Makefile: make upload-lambda
  bucket = aws_s3_bucket.compiler-explorer.bucket
  key    = "lambdas/lambda-package.zip"
}

resource "aws_lambda_function" "cloudwatch_to_discord" {
  description       = "Dispatch cloudwatch messages to discord"
  s3_bucket         = data.aws_s3_bucket_object.lambda_zip.bucket
  s3_key            = data.aws_s3_bucket_object.lambda_zip.key
  s3_object_version = data.aws_s3_bucket_object.lambda_zip.version_id
  function_name     = "cloudwatch_to_discord"
  role              = aws_iam_role.iam_for_lambda.arn
  handler           = "cloudwatch_to_discord.lambda_handler"

  source_code_hash = filebase64sha256("../.dist/lambda-package.zip")

  runtime = "python3.8"

  environment {
    variables = {
      WEBHOOK_URL = data.aws_ssm_parameter.discord_webhook_url.value
    }
  }
}

resource "aws_lambda_permission" "with_sns" {
  statement_id  = "AllowExecutionFromSNS"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.cloudwatch_to_discord.arn
  principal     = "sns.amazonaws.com"
  source_arn    = data.aws_sns_topic.alert.arn
}
