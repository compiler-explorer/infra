# Blue-Green deployment infrastructure for Windows environments
# Uses the blue_green module to create matching blue and green infrastructure

# Windows Test Environment
module "wintest_blue_green" {
  source = "./modules/blue_green"

  environment               = "wintest"
  vpc_id                    = module.ce_network.vpc.id
  launch_template_id        = aws_launch_template.CompilerExplorer-wintest.id
  subnets                   = local.subnets
  asg_max_size              = 4
  initial_desired_capacity  = 0
  health_check_grace_period = 300  # Override grace period for Windows test
  default_cooldown          = local.cooldown
  enabled_metrics           = local.common_enabled_metrics
  initial_active_color      = "blue"
}

# Windows Staging Environment
module "winstaging_blue_green" {
  source = "./modules/blue_green"

  environment               = "winstaging"
  vpc_id                    = module.ce_network.vpc.id
  launch_template_id        = aws_launch_template.CompilerExplorer-winstaging.id
  subnets                   = local.subnets
  asg_max_size              = 4
  initial_desired_capacity  = 0
  health_check_grace_period = 500  # Override grace period for Windows staging
  default_cooldown          = local.cooldown
  enabled_metrics           = local.common_enabled_metrics
  initial_active_color      = "blue"
}

# Windows Production Environment
module "winprod_blue_green" {
  source = "./modules/blue_green"

  environment               = "winprod"
  vpc_id                    = module.ce_network.vpc.id
  launch_template_id        = aws_launch_template.CompilerExplorer-winprod.id
  subnets                   = local.subnets
  asg_max_size              = 8
  initial_desired_capacity  = 0
  health_check_grace_period = local.win_grace_period
  default_cooldown          = local.cooldown
  enabled_metrics           = local.common_enabled_metrics
  initial_active_color      = "blue"

  # Mixed instances configuration for Windows production
  use_mixed_instances_policy               = true
  on_demand_base_capacity                  = 0
  on_demand_percentage_above_base_capacity = 0
  spot_allocation_strategy                 = "price-capacity-optimized"

  mixed_instances_overrides = [
    { instance_type = "m5zn.large" },
    { instance_type = "m5.large" },
    { instance_type = "m5n.large" },
    { instance_type = "m6i.large" },
    { instance_type = "m6id.large" },
    { instance_type = "m6in.large" }
  ]

  # Enable auto-scaling policy for Windows production
  enable_autoscaling_policy = true
  autoscaling_target_cpu    = 50.0
}
