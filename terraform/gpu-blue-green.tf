# Blue-Green deployment infrastructure for GPU environment
# Uses the blue_green module to create matching blue and green infrastructure

module "gpu_blue_green" {
  source = "./modules/blue_green"

  environment               = "gpu"
  vpc_id                    = module.ce_network.vpc.id
  launch_template_id        = aws_launch_template.CompilerExplorer-prod-gpu.id
  subnets                   = local.subnets
  asg_max_size              = 4
  initial_desired_capacity  = 0
  health_check_grace_period = local.grace_period
  default_cooldown          = local.cooldown
  enabled_metrics           = local.common_enabled_metrics
  initial_active_color      = "blue"

  # Mixed instances configuration for GPU environment
  use_mixed_instances_policy               = true
  on_demand_base_capacity                  = 1
  on_demand_percentage_above_base_capacity = 0
  spot_allocation_strategy                 = "price-capacity-optimized"

  mixed_instances_overrides = [
    { instance_type = "g4dn.xlarge" },
    { instance_type = "g4dn.2xlarge" }
  ]

  # Enable auto-scaling policy for GPU environment
  enable_autoscaling_policy = true
  autoscaling_target_cpu    = 50.0
}