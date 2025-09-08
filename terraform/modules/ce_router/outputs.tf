output "autoscaling_group_name" {
  description = "Name of the ce-router Auto Scaling Group"
  value       = aws_autoscaling_group.ce_router.name
}

output "autoscaling_group_arn" {
  description = "ARN of the ce-router Auto Scaling Group"
  value       = aws_autoscaling_group.ce_router.arn
}

output "target_group_arn" {
  description = "ARN of the ce-router target group"
  value       = aws_alb_target_group.ce_router.arn
}

output "target_group_name" {
  description = "Name of the ce-router target group"
  value       = aws_alb_target_group.ce_router.name
}
