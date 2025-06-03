output "target_group_arns" {
  description = "Map of color to target group ARN"
  value = {
    for color, tg in aws_alb_target_group.color : color => tg.arn
  }
}

output "target_group_names" {
  description = "Map of color to target group name"
  value = {
    for color, tg in aws_alb_target_group.color : color => tg.name
  }
}

output "asg_names" {
  description = "Map of color to ASG name"
  value = {
    for color, asg in aws_autoscaling_group.color : color => asg.name
  }
}

output "active_color_parameter_name" {
  description = "SSM parameter name for active color"
  value       = aws_ssm_parameter.active_color.name
}

output "active_target_group_parameter_name" {
  description = "SSM parameter name for active target group"
  value       = aws_ssm_parameter.active_target_group.name
}

output "active_target_group_arn" {
  description = "Currently active target group ARN (from SSM parameter)"
  value       = data.aws_ssm_parameter.active_tg.value
}