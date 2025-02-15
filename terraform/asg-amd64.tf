resource "aws_autoscaling_group" "prod-mixed" {
  lifecycle {
    create_before_destroy = true
  }

  default_cooldown          = local.cooldown
  health_check_grace_period = local.grace_period
  health_check_type         = "ELB"
  max_size                  = 24
  min_size                  = 2
  // Made two after @apmorton suggestion to cover edge cases of "last node unhealthy"
  name                = "prod"
  vpc_zone_identifier = local.subnets

  mixed_instances_policy {
    instances_distribution {
      // This base value is zero so we don't have any non-spot instances. We may wish to bump this if we have issues
      // getting spot capacity.
      on_demand_allocation_strategy            = "lowest-price"
      on_demand_base_capacity                  = 0
      on_demand_percentage_above_base_capacity = 0
      spot_allocation_strategy                 = "price-capacity-optimized"
      spot_instance_pools                      = 0
    }
    launch_template {
      launch_template_specification {
        launch_template_id = aws_launch_template.CompilerExplorer-prod.id
        version            = "$Latest"
      }
      // As of March 14 2023, we started seeing EFS issues running out of burst credit. We believe it's to do with
      // machines no longer having enough RAM to reasonably FS cache on top of all the other stuff they're doing.
      // We're bumping to m* instances from c* to give us more headroom.
      override {
        instance_type = "m5zn.large"
      }
      override {
        instance_type = "m5.large"
      }
      override {
        instance_type = "m5n.large"
      }
      override {
        instance_type = "m5d.large"
      }
      override {
        instance_type = "m5a.large"
      }
      override {
        instance_type = "m5ad.large"
      }
      override {
        instance_type = "m6a.large"
      }
      override {
        instance_type = "m6i.large"
      }
      override {
        instance_type = "m6id.large"
      }
      override {
        instance_type = "m6in.large"
      }
      override {
        instance_type = "m7i-flex.large"
      }
      override {
        instance_type = "m7i.large"
      }
      override {
        instance_type = "m5dn.large"
      }
      override {
        instance_type = "r6a.large"
      }
      override {
        instance_type = "i3.large"
      }
      override {
        instance_type = "i4i.large"
      }
    }
  }

  enabled_metrics = local.common_enabled_metrics

  target_group_arns = [aws_alb_target_group.ce["prod"].arn]
}

resource "aws_autoscaling_policy" "prod-mixed" {
  lifecycle {
    create_before_destroy = true
  }

  autoscaling_group_name    = aws_autoscaling_group.prod-mixed.name
  name                      = "cpu-tracker"
  policy_type               = "TargetTrackingScaling"
  estimated_instance_warmup = local.grace_period + 30
  target_tracking_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ASGAverageCPUUtilization"
    }
    target_value = 50.0
  }
}

resource "aws_autoscaling_group" "beta" {
  lifecycle {
    create_before_destroy = true
  }

  default_cooldown          = local.cooldown
  health_check_grace_period = local.grace_period
  health_check_type         = "ELB"
  launch_template {
    id      = aws_launch_template.CompilerExplorer-beta.id
    version = "$Latest"
  }

  max_size            = 4
  min_size            = 0
  name                = "beta"
  vpc_zone_identifier = local.subnets

  target_group_arns = [aws_alb_target_group.ce["beta"].arn]
}

resource "aws_autoscaling_group" "staging" {
  lifecycle {
    create_before_destroy = true
  }

  default_cooldown          = local.cooldown
  health_check_grace_period = local.grace_period
  health_check_type         = "ELB"
  launch_template {
    id      = aws_launch_template.CompilerExplorer-staging.id
    version = "$Latest"
  }
  max_size            = 4
  min_size            = 0
  name                = "staging"
  vpc_zone_identifier = local.subnets

  target_group_arns = [aws_alb_target_group.ce["staging"].arn]
}
