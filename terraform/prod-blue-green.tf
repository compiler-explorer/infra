# Blue-Green deployment infrastructure for Production environment
# Uses the blue_green module to create matching blue and green infrastructure
#
# NOTE: This creates the blue-green infrastructure but production traffic
# still flows through the old prod-mixed ASG. To migrate:
# 1. Apply this terraform to create the blue-green resources
# 2. Test the blue-green module thoroughly with beta
# 3. Follow migration steps in docs/blue_green_deployment_strategy.md
# 4. Update alb.tf to use blue-green target groups
# 5. Remove the old prod-mixed ASG from asg-amd64.tf

module "prod_blue_green" {
  source = "./modules/blue_green"

  environment               = "prod"
  vpc_id                    = module.ce_network.vpc.id
  launch_template_id        = aws_launch_template.CompilerExplorer-prod.id
  subnets                   = local.subnets
  asg_max_size              = 40
  initial_desired_capacity  = 0
  health_check_grace_period = local.grace_period
  default_cooldown          = local.cooldown
  enabled_metrics           = local.common_enabled_metrics
  initial_active_color      = "blue"

  # Mixed instances configuration for production
  use_mixed_instances_policy               = true
  on_demand_base_capacity                  = 0
  on_demand_percentage_above_base_capacity = 0
  spot_allocation_strategy                 = "price-capacity-optimized"

  mixed_instances_overrides = [
    { instance_type = "m5zn.large" },
    { instance_type = "m5.large" },
    { instance_type = "m5n.large" },
    { instance_type = "m5d.large" },
    { instance_type = "m5a.large" },
    { instance_type = "m5ad.large" },
    { instance_type = "m6a.large" },
    { instance_type = "m6i.large" },
    { instance_type = "m6id.large" },
    { instance_type = "m6in.large" },
    { instance_type = "m7i-flex.large" },
    { instance_type = "m7i.large" },
    { instance_type = "m5dn.large" },
    { instance_type = "r6a.large" },
    { instance_type = "i3.large" },
    { instance_type = "i4i.large" }
  ]

  # Enable auto-scaling policy for production
  enable_autoscaling_policy = true
  autoscaling_target_cpu    = 50.0
}
