# Blue-Green deployment infrastructure for AArch64 environments
# Uses the blue_green module to create matching blue and green infrastructure

# AArch64 Production Environment
module "aarch64prod_blue_green" {
  source = "./modules/blue_green"

  environment               = "aarch64prod"
  vpc_id                    = module.ce_network.vpc.id
  launch_template_id        = aws_launch_template.CompilerExplorer-aarch64prod.id
  subnets                   = local.subnets
  asg_max_size              = 6
  initial_desired_capacity  = 0
  health_check_grace_period = local.grace_period
  default_cooldown          = local.cooldown
  enabled_metrics           = local.common_enabled_metrics
  initial_active_color      = "blue"

  # Mixed instances configuration for AArch64 production
  use_mixed_instances_policy               = true
  on_demand_base_capacity                  = 0
  on_demand_percentage_above_base_capacity = 0
  spot_allocation_strategy                 = "price-capacity-optimized"

  mixed_instances_overrides = [
    { instance_type = "r7g.medium" }
  ]

  # Custom auto-scaling policy matching existing setup - will be added separately
  enable_autoscaling_policy = false
}

# AArch64 Staging Environment
module "aarch64staging_blue_green" {
  source = "./modules/blue_green"

  environment               = "aarch64staging"
  vpc_id                    = module.ce_network.vpc.id
  launch_template_id        = aws_launch_template.CompilerExplorer-aarch64staging.id
  subnets                   = local.subnets
  asg_max_size              = 4
  initial_desired_capacity  = 0
  health_check_grace_period = local.grace_period
  default_cooldown          = local.cooldown
  enabled_metrics           = local.common_enabled_metrics
  initial_active_color      = "blue"

  # Mixed instances configuration for AArch64 staging
  use_mixed_instances_policy               = true
  on_demand_base_capacity                  = 0
  on_demand_percentage_above_base_capacity = 0
  spot_allocation_strategy                 = "price-capacity-optimized"

  mixed_instances_overrides = [
    { instance_type = "r7g.medium" }
  ]

  # Custom auto-scaling policy matching existing setup - will be added separately
  enable_autoscaling_policy = false
}

# Custom auto-scaling policies for AArch64 environments (matching existing SQS-based scaling)
# AArch64 Production
resource "aws_autoscaling_policy" "aarch64prod_blue" {
  lifecycle {
    create_before_destroy = true
  }

  autoscaling_group_name    = module.aarch64prod_blue_green.blue_asg_name
  name                      = "aarch64prod-mq-tracker-blue"
  policy_type               = "TargetTrackingScaling"
  estimated_instance_warmup = local.cooldown

  target_tracking_configuration {
    target_value = 3
    customized_metric_specification {
      metrics {
        label = "Get the queue size (the number of messages waiting to be processed)"
        id    = "m1"
        metric_stat {
          metric {
            namespace   = "AWS/SQS"
            metric_name = "ApproximateNumberOfMessagesVisible"
            dimensions {
              name  = "QueueName"
              value = aws_sqs_queue.prod-execqueue-aarch64-linux-cpu.name
            }
          }
          stat = "Sum"
        }
        return_data = false
      }
      metrics {
        label = "Get the group size (the number of InService instances)"
        id    = "m2"
        metric_stat {
          metric {
            namespace   = "AWS/AutoScaling"
            metric_name = "GroupInServiceInstances"
            dimensions {
              name  = "AutoScalingGroupName"
              value = module.aarch64prod_blue_green.blue_asg_name
            }
          }
          stat = "Average"
        }
        return_data = false
      }
      metrics {
        label       = "Calculate the backlog per instance"
        id          = "e1"
        expression  = "m1 / m2"
        return_data = true
      }
    }
  }
}

resource "aws_autoscaling_policy" "aarch64prod_green" {
  lifecycle {
    create_before_destroy = true
  }

  autoscaling_group_name    = module.aarch64prod_blue_green.green_asg_name
  name                      = "aarch64prod-mq-tracker-green"
  policy_type               = "TargetTrackingScaling"
  estimated_instance_warmup = local.cooldown

  target_tracking_configuration {
    target_value = 3
    customized_metric_specification {
      metrics {
        label = "Get the queue size (the number of messages waiting to be processed)"
        id    = "m1"
        metric_stat {
          metric {
            namespace   = "AWS/SQS"
            metric_name = "ApproximateNumberOfMessagesVisible"
            dimensions {
              name  = "QueueName"
              value = aws_sqs_queue.prod-execqueue-aarch64-linux-cpu.name
            }
          }
          stat = "Sum"
        }
        return_data = false
      }
      metrics {
        label = "Get the group size (the number of InService instances)"
        id    = "m2"
        metric_stat {
          metric {
            namespace   = "AWS/AutoScaling"
            metric_name = "GroupInServiceInstances"
            dimensions {
              name  = "AutoScalingGroupName"
              value = module.aarch64prod_blue_green.green_asg_name
            }
          }
          stat = "Average"
        }
        return_data = false
      }
      metrics {
        label       = "Calculate the backlog per instance"
        id          = "e1"
        expression  = "m1 / m2"
        return_data = true
      }
    }
  }
}

# AArch64 Staging
resource "aws_autoscaling_policy" "aarch64staging_blue" {
  lifecycle {
    create_before_destroy = true
  }

  autoscaling_group_name    = module.aarch64staging_blue_green.blue_asg_name
  name                      = "aarch64staging-mq-tracker-blue"
  policy_type               = "TargetTrackingScaling"
  estimated_instance_warmup = local.cooldown

  target_tracking_configuration {
    target_value = 3
    customized_metric_specification {
      metrics {
        label = "Get the queue size (the number of messages waiting to be processed)"
        id    = "m1"
        metric_stat {
          metric {
            namespace   = "AWS/SQS"
            metric_name = "ApproximateNumberOfMessagesVisible"
            dimensions {
              name  = "QueueName"
              value = aws_sqs_queue.staging-execqueue-aarch64-linux-cpu.name
            }
          }
          stat = "Sum"
        }
        return_data = false
      }
      metrics {
        label = "Get the group size (the number of InService instances)"
        id    = "m2"
        metric_stat {
          metric {
            namespace   = "AWS/AutoScaling"
            metric_name = "GroupInServiceInstances"
            dimensions {
              name  = "AutoScalingGroupName"
              value = module.aarch64staging_blue_green.blue_asg_name
            }
          }
          stat = "Average"
        }
        return_data = false
      }
      metrics {
        label       = "Calculate the backlog per instance"
        id          = "e1"
        expression  = "m1 / m2"
        return_data = true
      }
    }
  }
}

resource "aws_autoscaling_policy" "aarch64staging_green" {
  lifecycle {
    create_before_destroy = true
  }

  autoscaling_group_name    = module.aarch64staging_blue_green.green_asg_name
  name                      = "aarch64staging-mq-tracker-green"
  policy_type               = "TargetTrackingScaling"
  estimated_instance_warmup = local.cooldown

  target_tracking_configuration {
    target_value = 3
    customized_metric_specification {
      metrics {
        label = "Get the queue size (the number of messages waiting to be processed)"
        id    = "m1"
        metric_stat {
          metric {
            namespace   = "AWS/SQS"
            metric_name = "ApproximateNumberOfMessagesVisible"
            dimensions {
              name  = "QueueName"
              value = aws_sqs_queue.staging-execqueue-aarch64-linux-cpu.name
            }
          }
          stat = "Sum"
        }
        return_data = false
      }
      metrics {
        label = "Get the group size (the number of InService instances)"
        id    = "m2"
        metric_stat {
          metric {
            namespace   = "AWS/AutoScaling"
            metric_name = "GroupInServiceInstances"
            dimensions {
              name  = "AutoScalingGroupName"
              value = module.aarch64staging_blue_green.green_asg_name
            }
          }
          stat = "Average"
        }
        return_data = false
      }
      metrics {
        label       = "Calculate the backlog per instance"
        id          = "e1"
        expression  = "m1 / m2"
        return_data = true
      }
    }
  }
}
