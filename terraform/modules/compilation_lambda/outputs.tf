# Outputs for compilation Lambda module

# Blue queue outputs
output "sqs_queue_blue_id" {
  description = "Blue SQS queue ID"
  value       = aws_sqs_queue.compilation_queue_blue.id
}

output "sqs_queue_blue_arn" {
  description = "Blue SQS queue ARN"
  value       = aws_sqs_queue.compilation_queue_blue.arn
}

output "sqs_queue_blue_name" {
  description = "Blue SQS queue name"
  value       = aws_sqs_queue.compilation_queue_blue.name
}

# Green queue outputs
output "sqs_queue_green_id" {
  description = "Green SQS queue ID"
  value       = aws_sqs_queue.compilation_queue_green.id
}

output "sqs_queue_green_arn" {
  description = "Green SQS queue ARN"
  value       = aws_sqs_queue.compilation_queue_green.arn
}

output "sqs_queue_green_name" {
  description = "Green SQS queue name"
  value       = aws_sqs_queue.compilation_queue_green.name
}

output "lambda_function_arn" {
  description = "Lambda function ARN"
  value       = aws_lambda_function.compilation.arn
}

output "lambda_function_name" {
  description = "Lambda function name"
  value       = aws_lambda_function.compilation.function_name
}

output "alb_target_group_arn" {
  description = "ALB target group ARN"
  value       = aws_alb_target_group.compilation_lambda.arn
}

output "cloudwatch_log_group_name" {
  description = "CloudWatch log group name"
  value       = aws_cloudwatch_log_group.compilation.name
}
