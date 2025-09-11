variable "temp_storage_retention_days" {
  description = "Number of days to retain overflow messages in S3 before automatic deletion"
  type        = number
  default     = 1

  validation {
    condition     = var.temp_storage_retention_days >= 1 && var.temp_storage_retention_days <= 30
    error_message = "Retention days must be between 1 and 30 days."
  }
}

variable "sqs_overflow_key_prefix" {
  description = "S3 key prefix for SQS overflow messages in temp storage"
  type        = string
  default     = "sqs-overflow/"
}
