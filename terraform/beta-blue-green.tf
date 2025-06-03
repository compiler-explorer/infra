# Blue-Green deployment infrastructure for Beta environment
# Uses the blue_green module to create matching blue and green infrastructure

module "beta_blue_green" {
  source = "./modules/blue_green"

  environment               = "beta"
  vpc_id                    = module.ce_network.vpc.id
  launch_template_id        = aws_launch_template.CompilerExplorer-beta.id
  subnets                   = local.subnets
  asg_max_size              = 4
  initial_desired_capacity  = 0
  health_check_grace_period = local.grace_period
  default_cooldown          = local.cooldown
  enabled_metrics           = local.common_enabled_metrics
  initial_active_color      = "blue"
}

# Outputs for reference and use in other resources
output "beta_blue_target_group_arn" {
  value       = module.beta_blue_green.target_group_arns["blue"]
  description = "ARN of the beta blue target group"
}

output "beta_green_target_group_arn" {
  value       = module.beta_blue_green.target_group_arns["green"]
  description = "ARN of the beta green target group"
}

output "beta_active_target_group_arn" {
  value       = module.beta_blue_green.active_target_group_arn
  description = "Currently active target group ARN for beta"
}

output "beta_active_color" {
  value       = data.aws_ssm_parameter.beta_active_color.value
  description = "Currently active color for beta environment"
  sensitive   = true
}

# Data source for active color parameter (for compatibility)
data "aws_ssm_parameter" "beta_active_color" {
  name = module.beta_blue_green.active_color_parameter_name
}
