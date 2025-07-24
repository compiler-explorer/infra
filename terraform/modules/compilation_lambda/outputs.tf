# Outputs for compilation Lambda module

output "sqs_queue_id" {
  description = "SQS queue ID"
  value       = aws_sqs_queue.compilation_queue.id
}

output "sqs_queue_arn" {
  description = "SQS queue ARN"
  value       = aws_sqs_queue.compilation_queue.arn
}

output "sqs_queue_name" {
  description = "SQS queue name"
  value       = aws_sqs_queue.compilation_queue.name
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
