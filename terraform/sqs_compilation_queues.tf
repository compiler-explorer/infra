# SQS Queues for Compilation Lambda Infrastructure
# These queues receive compilation requests from the Lambda functions

# Beta environment compilation queue
resource "aws_sqs_queue" "compilation_queue_beta" {
  name                        = "beta-compilation-queue.fifo"
  fifo_queue                  = true
  content_based_deduplication = false
  message_retention_seconds   = 1800  # 30 minutes
  visibility_timeout_seconds  = 120   # 2 minutes to process compilation
  
  
  tags = {
    Environment = "beta"
    Purpose     = "compilation-requests"
  }
}

# Staging environment compilation queue
resource "aws_sqs_queue" "compilation_queue_staging" {
  name                        = "staging-compilation-queue.fifo"
  fifo_queue                  = true
  content_based_deduplication = false
  message_retention_seconds   = 1800  # 30 minutes
  visibility_timeout_seconds  = 120   # 2 minutes
  
  
  tags = {
    Environment = "staging"
    Purpose     = "compilation-requests"
  }
}

# Production environment compilation queue
resource "aws_sqs_queue" "compilation_queue_prod" {
  name                        = "prod-compilation-queue.fifo"
  fifo_queue                  = true
  content_based_deduplication = false
  message_retention_seconds   = 1800  # 30 minutes
  visibility_timeout_seconds  = 120   # 2 minutes
  
  
  tags = {
    Environment = "prod"
    Purpose     = "compilation-requests"
  }
}


# Outputs for use in other modules
output "compilation_queue_beta_id" {
  value = aws_sqs_queue.compilation_queue_beta.id
}

output "compilation_queue_staging_id" {
  value = aws_sqs_queue.compilation_queue_staging.id
}

output "compilation_queue_prod_id" {
  value = aws_sqs_queue.compilation_queue_prod.id
}

output "compilation_queue_beta_arn" {
  value = aws_sqs_queue.compilation_queue_beta.arn
}

output "compilation_queue_staging_arn" {
  value = aws_sqs_queue.compilation_queue_staging.arn
}

output "compilation_queue_prod_arn" {
  value = aws_sqs_queue.compilation_queue_prod.arn
}

