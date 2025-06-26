# Variables for compilation Lambda module

variable "environment" {
  description = "Environment name for resource naming and tagging"
  type        = string
}

variable "websocket_url" {
  description = "WebSocket URL for events system"
  type        = string
}

variable "alb_listener_arn" {
  description = "ALB listener ARN for routing rules"
  type        = string
}

variable "enable_alb_listener" {
  description = "Whether to create ALB listener rule"
  type        = bool
  default     = false
}

variable "alb_priority" {
  description = "ALB listener rule priority"
  type        = number
}

variable "alb_path_patterns" {
  description = "List of path patterns for ALB listener rule"
  type        = list(string)
  default     = []
}

variable "lambda_timeout" {
  description = "Lambda function timeout in seconds"
  type        = number
  default     = 120
}

variable "lambda_retry_count" {
  description = "Number of WebSocket retry attempts"
  type        = string
  default     = "2"
}

variable "lambda_timeout_seconds" {
  description = "WebSocket response timeout in seconds"
  type        = string
  default     = "90"
}

variable "sqs_message_retention_seconds" {
  description = "SQS message retention period in seconds"
  type        = number
  default     = 60 # 1 minute
}

variable "sqs_visibility_timeout_seconds" {
  description = "SQS visibility timeout in seconds"
  type        = number
  default     = 5 # 5 seconds
}

variable "cloudwatch_log_retention_days" {
  description = "CloudWatch log retention period in days"
  type        = number
  default     = 14
}

variable "s3_bucket" {
  description = "S3 bucket for Lambda package"
  type        = string
}

variable "lambda_package_key" {
  description = "S3 key for Lambda package"
  type        = string
  default     = "lambdas/compilation-lambda-package.zip"
}

variable "lambda_package_sha_key" {
  description = "S3 key for Lambda package SHA"
  type        = string
  default     = "lambdas/compilation-lambda-package.zip.sha256"
}

variable "iam_role_arn" {
  description = "IAM role ARN for Lambda execution"
  type        = string
}

variable "tags" {
  description = "Additional tags to apply to resources"
  type        = map(string)
  default     = {}
}
