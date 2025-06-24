# Compilation Lambda Infrastructure for All Environments
# Uses the compilation_lambda module to create consistent infrastructure

# Beta Environment
module "compilation_lambda_beta" {
  source = "./modules/compilation_lambda"

  environment         = "beta"
  websocket_url       = "wss://events.godbolt.org/beta"
  alb_listener_arn    = aws_alb_listener.compiler-explorer-alb-listen-https.arn
  enable_alb_listener = true
  alb_priority        = 10
  alb_path_patterns = [
    "/beta/api/compilers/*/compile",
    "/beta/api/compilers/*/cmake"
  ]
  s3_bucket    = aws_s3_bucket.compiler-explorer.bucket
  iam_role_arn = aws_iam_role.iam_for_lambda.arn

  tags = {
    Project = "compiler-explorer"
  }
}

# Staging Environment
module "compilation_lambda_staging" {
  source = "./modules/compilation_lambda"

  environment         = "staging"
  websocket_url       = "wss://events.godbolt.org/staging"
  alb_listener_arn    = aws_alb_listener.compiler-explorer-alb-listen-https.arn
  enable_alb_listener = false # Disabled initially
  alb_priority        = 12
  alb_path_patterns = [
    "/staging/api/compilers/*/compile",
    "/staging/api/compilers/*/cmake"
  ]
  s3_bucket    = aws_s3_bucket.compiler-explorer.bucket
  iam_role_arn = aws_iam_role.iam_for_lambda.arn

  tags = {
    Project = "compiler-explorer"
  }
}

# Production Environment
module "compilation_lambda_prod" {
  source = "./modules/compilation_lambda"

  environment         = "prod"
  websocket_url       = "wss://events.godbolt.org/"
  alb_listener_arn    = aws_alb_listener.compiler-explorer-alb-listen-https.arn
  enable_alb_listener = false # Disabled initially
  alb_priority        = 4
  alb_path_patterns = [
    "/api/compilers/*/compile",
    "/api/compilers/*/cmake"
  ]
  s3_bucket    = aws_s3_bucket.compiler-explorer.bucket
  iam_role_arn = aws_iam_role.iam_for_lambda.arn

  tags = {
    Project = "compiler-explorer"
  }
}

# Updated IAM policy to use module outputs
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
