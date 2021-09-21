locals {
  subnets      = local.all_subnet_ids
  grace_period = 180
  cooldown     = 180
}

resource "aws_autoscaling_group" "prod-mixed" {
  lifecycle {
    create_before_destroy = true
  }

  default_cooldown          = local.cooldown
  health_check_grace_period = local.grace_period
  health_check_type         = "ELB"
  max_size                  = 16
  min_size                  = 2
  // Made two after @apmorton suggestion to cover edge cases of "last node unhealthy"
  name                      = "prod"
  vpc_zone_identifier       = local.subnets

  mixed_instances_policy {
    instances_distribution {
      on_demand_allocation_strategy            = "prioritized"
      // This base value is zero so we don't have any non-spot instances. We may wish to bump this if we have issues
      // getting spot capacity.
      on_demand_base_capacity                  = 0
      on_demand_percentage_above_base_capacity = 0
      spot_allocation_strategy                 = "lowest-price"
      spot_instance_pools                      = 2
      // we may consider upping this if we have issues fulfilling
      spot_max_price                           = local.spot_price
    }
    launch_template {
      launch_template_specification {
        launch_template_id = aws_launch_template.CompilerExplorer-prod.id
        version            = "$Latest"
      }
    }
  }

  enabled_metrics = [
    "GroupDesiredCapacity",
    "GroupInServiceCapacity",
    "GroupInServiceInstances",
    "GroupMaxSize",
    "GroupMinSize",
    "GroupPendingCapacity",
    "GroupPendingInstances",
    "GroupStandbyCapacity",
    "GroupStandbyInstances",
    "GroupTerminatingCapacity",
    "GroupTerminatingInstances",
    "GroupTotalCapacity",
    "GroupTotalInstances",
  ]

  target_group_arns = [module.main.prod_target_group.arn]
}

resource "aws_autoscaling_policy" "prod-mixed" {
  lifecycle {
    create_before_destroy = true
  }

  autoscaling_group_name    = aws_autoscaling_group.prod-mixed.name
  name                      = "cpu-tracker"
  policy_type               = "TargetTrackingScaling"
  estimated_instance_warmup = 1000
  target_tracking_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ASGAverageCPUUtilization"
    }
    target_value = 40.0
  }
}
