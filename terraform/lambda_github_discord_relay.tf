# Relays the org-wide GitHub webhook to Discord's #github-bot, dropping events from non-public repos.
# GitHub org webhooks can't be filtered by repo visibility, so the org hook points here instead of at Discord.
# See lambda/github_to_discord.py. Both SSM parameters must exist (SecureString) before this is applied:
#   /admin/github_bot_discord_webhook_url   the Discord webhook for #github-bot (without the trailing /github)
#   /admin/github_bot_relay_secret          shared secret configured on the GitHub org webhook
data "aws_ssm_parameter" "github_bot_discord_webhook_url" {
  name = "/admin/github_bot_discord_webhook_url"
}

data "aws_ssm_parameter" "github_bot_relay_secret" {
  name = "/admin/github_bot_relay_secret"
}

# Internet-facing, so deliberately not the shared iam_for_lambda role (S3, SQS, DynamoDB, SNS...): logging only.
resource "aws_iam_role" "github_to_discord" {
  name               = "iam_for_github_to_discord"
  assume_role_policy = data.aws_iam_policy_document.aws_lambda_trust_policy.json
}

resource "aws_iam_role_policy_attachment" "github_to_discord_logs" {
  role       = aws_iam_role.github_to_discord.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_cloudwatch_log_group" "github_to_discord" {
  name              = "/aws/lambda/github_to_discord"
  retention_in_days = 14
}

resource "aws_lambda_function" "github_to_discord" {
  description       = "Relay GitHub org webhooks to Discord, dropping anything from non-public repositories"
  s3_bucket         = data.aws_s3_object.lambda_zip.bucket
  s3_key            = data.aws_s3_object.lambda_zip.key
  s3_object_version = data.aws_s3_object.lambda_zip.version_id
  source_code_hash  = chomp(data.aws_s3_object.lambda_zip_sha.body)
  function_name     = "github_to_discord"
  role              = aws_iam_role.github_to_discord.arn
  handler           = "github_to_discord.lambda_handler"
  # GitHub abandons a delivery after 10s; see DISCORD_TIMEOUT_SECONDS in the handler.
  timeout = 15
  # The URL is public and unauthenticated: cap what a flood can bill, and keep it from starving the account's
  # shared concurrency pool. Excess requests get a 429, which is fine as GitHub deliveries can be redelivered.
  reserved_concurrent_executions = 5

  runtime = "python3.12"

  environment {
    variables = {
      DISCORD_WEBHOOK_URL   = data.aws_ssm_parameter.github_bot_discord_webhook_url.value
      GITHUB_WEBHOOK_SECRET = data.aws_ssm_parameter.github_bot_relay_secret.value
    }
  }
  depends_on = [aws_cloudwatch_log_group.github_to_discord]
}

# The GitHub hook must be configured with content type application/json: the signature is over the raw body and
# the form-encoded variant wraps the payload, so it would be rejected as invalid JSON.
# Public by necessity (GitHub can't sign AWS requests); the handler authenticates callers with the HMAC signature.
resource "aws_lambda_function_url" "github_to_discord" {
  function_name      = aws_lambda_function.github_to_discord.function_name
  authorization_type = "NONE"
}

resource "aws_lambda_permission" "github_to_discord_url" {
  statement_id           = "AllowPublicFunctionUrl"
  action                 = "lambda:InvokeFunctionUrl"
  function_name          = aws_lambda_function.github_to_discord.function_name
  principal              = "*"
  function_url_auth_type = "NONE"
}

resource "aws_lambda_permission" "github_to_discord_invoke" {
  statement_id             = "AllowPublicInvokeViaFunctionUrl"
  action                   = "lambda:InvokeFunction"
  function_name            = aws_lambda_function.github_to_discord.function_name
  principal                = "*"
  invoked_via_function_url = true
}

output "github_to_discord_url" {
  description = "Payload URL for the GitHub org webhook"
  value       = aws_lambda_function_url.github_to_discord.function_url
}
