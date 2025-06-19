# Blue-Green deployment infrastructure for Staging environment
# Uses the blue_green module to create matching blue and green infrastructure

module "staging_blue_green" {
  source = "./modules/blue_green"

  environment               = "staging"
  vpc_id                    = module.ce_network.vpc.id
  launch_template_id        = aws_launch_template.CompilerExplorer-staging.id
  subnets                   = local.subnets
  asg_max_size              = 4
  initial_desired_capacity  = 0
  health_check_grace_period = local.grace_period
  default_cooldown          = local.cooldown
  enabled_metrics           = local.common_enabled_metrics
  initial_active_color      = "blue"
}
