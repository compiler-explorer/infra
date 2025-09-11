variable "sqs_overflow_retention_days" {
  description = "Number of days to retain overflow messages in S3 before automatic deletion"
  type        = number
  default     = 7

  validation {
    condition     = var.sqs_overflow_retention_days >= 1 && var.sqs_overflow_retention_days <= 30
    error_message = "Retention days must be between 1 and 30 days."
  }
}

variable "sqs_max_message_size" {
  description = "Maximum SQS message size in bytes before overflow to S3 (default: 256KB)"
  type        = number
  default     = 262144

  validation {
    condition     = var.sqs_max_message_size >= 1024 && var.sqs_max_message_size <= 262144
    error_message = "Message size must be between 1KB and 256KB."
  }
}

variable "s3_overflow_key_prefix" {
  description = "S3 key prefix for overflow messages"
  type        = string
  default     = "messages/"
}
