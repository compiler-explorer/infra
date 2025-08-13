# Compilation Lambda Infrastructure for All Environments
# Uses the compilation_lambda module to create consistent infrastructure

# Beta Environment
module "compilation_lambda_beta" {
  source = "./modules/compilation_lambda"

  environment         = "beta"
  websocket_url       = "wss://events.compiler-explorer.com/prod" # All environments use the same WebSocket endpoint
  alb_listener_arn    = aws_alb_listener.compiler-explorer-alb-listen-https.arn
  enable_alb_listener = true
  alb_priority        = 91
  alb_path_patterns = [
    "/beta/api/compiler/*/compile",
    "/beta/api/compiler/*/cmake"
  ]
  s3_bucket                     = aws_s3_bucket.compiler-explorer.bucket
  iam_role_arn                  = aws_iam_role.iam_for_lambda.arn
  cloudwatch_log_retention_days = 1 # Minimum possible retention (1 day) for high-volume logging

  tags = {
    Project = "compiler-explorer"
  }
}

# Staging Environment
module "compilation_lambda_staging" {
  source = "./modules/compilation_lambda"

  environment         = "staging"
  websocket_url       = "wss://events.compiler-explorer.com/staging"
  alb_listener_arn    = aws_alb_listener.compiler-explorer-alb-listen-https.arn
  enable_alb_listener = true
  alb_priority        = 81
  alb_path_patterns = [
    "/staging/api/compiler/*/compile",
    "/staging/api/compiler/*/cmake"
  ]
  s3_bucket                     = aws_s3_bucket.compiler-explorer.bucket
  iam_role_arn                  = aws_iam_role.iam_for_lambda.arn
  cloudwatch_log_retention_days = 1 # Minimum possible retention (1 day) for high-volume logging

  tags = {
    Project = "compiler-explorer"
  }
}

# Production Environment
module "compilation_lambda_prod" {
  source = "./modules/compilation_lambda"

  environment         = "prod"
  websocket_url       = "wss://events.compiler-explorer.com/prod"
  alb_listener_arn    = aws_alb_listener.compiler-explorer-alb-listen-https.arn
  enable_alb_listener = true
  alb_priority        = 71
  alb_path_patterns = [
    "/killswitch-disabled-*"
  ]
  s3_bucket                     = aws_s3_bucket.compiler-explorer.bucket
  iam_role_arn                  = aws_iam_role.iam_for_lambda.arn
  cloudwatch_log_retention_days = 1 # Minimum possible retention (1 day) for high-volume logging

  tags = {
    Project = "compiler-explorer"
  }
}

# Updated IAM policy to use module outputs for all environments
data "aws_iam_policy_document" "compilation_lambda_sqs" {
  statement {
    sid = "SQSAccess"
    actions = [
      "sqs:SendMessage",
      "sqs:GetQueueAttributes"
    ]
    resources = [
      module.compilation_lambda_beta.sqs_queue_arn,
      module.compilation_lambda_staging.sqs_queue_arn,
      module.compilation_lambda_prod.sqs_queue_arn
    ]
  }
}

resource "aws_iam_policy" "compilation_lambda_sqs" {
  name        = "compilation_lambda_sqs"
  description = "Allow compilation Lambda to send messages to SQS queues"
  policy      = data.aws_iam_policy_document.compilation_lambda_sqs.json
}

resource "aws_iam_role_policy_attachment" "compilation_lambda_sqs" {
  role       = aws_iam_role.iam_for_lambda.name
  policy_arn = aws_iam_policy.compilation_lambda_sqs.arn
}

# IAM policy for compilation Lambda to access compiler routing table
data "aws_iam_policy_document" "compilation_lambda_routing" {
  statement {
    sid = "DynamoDBRouting"
    actions = [
      "dynamodb:GetItem"
    ]
    resources = [aws_dynamodb_table.compiler_routing.arn]
  }
  statement {
    sid = "STSAccess"
    actions = [
      "sts:GetCallerIdentity"
    ]
    resources = ["*"]
  }
}

resource "aws_iam_policy" "compilation_lambda_routing" {
  name        = "compilation_lambda_routing"
  description = "Allow compilation Lambda to access compiler routing table"
  policy      = data.aws_iam_policy_document.compilation_lambda_routing.json
}

resource "aws_iam_role_policy_attachment" "compilation_lambda_routing" {
  role       = aws_iam_role.iam_for_lambda.name
  policy_arn = aws_iam_policy.compilation_lambda_routing.arn
}

# IAM policy for compilation Lambda to read large results from S3 cache
data "aws_iam_policy_document" "compilation_lambda_s3_cache" {
  statement {
    sid = "S3CacheRead"
    actions = [
      "s3:GetObject",
      "s3:GetObjectVersion"
    ]
    resources = ["${aws_s3_bucket.storage-godbolt-org.arn}/cache/*"]
  }
  statement {
    sid = "S3CacheList"
    actions = [
      "s3:ListBucket"
    ]
    resources = [aws_s3_bucket.storage-godbolt-org.arn]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["cache/*"]
    }
  }
}

resource "aws_iam_policy" "compilation_lambda_s3_cache" {
  name        = "compilation_lambda_s3_cache"
  description = "Allow compilation Lambda to read large results from S3 cache"
  policy      = data.aws_iam_policy_document.compilation_lambda_s3_cache.json
}

resource "aws_iam_role_policy_attachment" "compilation_lambda_s3_cache" {
  role       = aws_iam_role.iam_for_lambda.name
  policy_arn = aws_iam_policy.compilation_lambda_s3_cache.arn
}

# Outputs for backward compatibility and ASG integration
output "compilation_queue_beta_id" {
  description = "Beta compilation queue ID"
  value       = module.compilation_lambda_beta.sqs_queue_id
}

output "compilation_queue_staging_id" {
  description = "Staging compilation queue ID"
  value       = module.compilation_lambda_staging.sqs_queue_id
}

output "compilation_queue_prod_id" {
  description = "Production compilation queue ID"
  value       = module.compilation_lambda_prod.sqs_queue_id
}

output "compilation_queue_beta_arn" {
  description = "Beta compilation queue ARN"
  value       = module.compilation_lambda_beta.sqs_queue_arn
}

output "compilation_queue_staging_arn" {
  description = "Staging compilation queue ARN"
  value       = module.compilation_lambda_staging.sqs_queue_arn
}

output "compilation_queue_prod_arn" {
  description = "Production compilation queue ARN"
  value       = module.compilation_lambda_prod.sqs_queue_arn
}

output "compilation_queue_beta_name" {
  description = "Beta compilation queue name"
  value       = module.compilation_lambda_beta.sqs_queue_name
}

output "compilation_queue_staging_name" {
  description = "Staging compilation queue name"
  value       = module.compilation_lambda_staging.sqs_queue_name
}

output "compilation_queue_prod_name" {
  description = "Production compilation queue name"
  value       = module.compilation_lambda_prod.sqs_queue_name
}
