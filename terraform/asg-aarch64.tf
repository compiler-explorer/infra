resource "aws_autoscaling_group" "aarch64prod-mixed" {
  lifecycle {
    create_before_destroy = true
  }

  default_cooldown          = local.cooldown
  health_check_grace_period = local.grace_period
  health_check_type         = "ELB"
  max_size                  = 6
  min_size                  = 0
  name                      = "aarch64prod"
  vpc_zone_identifier       = local.subnets

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
        launch_template_id = aws_launch_template.CompilerExplorer-aarch64prod.id
        version            = "$Latest"
      }
      override {
        instance_type = "r7g.medium"
      }
    }
  }

  enabled_metrics = local.common_enabled_metrics

  target_group_arns = [aws_alb_target_group.ce["aarch64prod"].arn]
}

resource "aws_autoscaling_policy" "aarch64prod-mixed" {
  lifecycle {
    create_before_destroy = true
  }

  autoscaling_group_name = aws_autoscaling_group.aarch64prod-mixed.name
  name                   = "aarch64prod-mq-tracker"
  policy_type            = "TargetTrackingScaling"
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
              value = aws_autoscaling_group.aarch64prod-mixed.name
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

resource "aws_autoscaling_group" "aarch64staging-mixed" {
  lifecycle {
    create_before_destroy = true
  }

  default_cooldown          = local.cooldown
  health_check_grace_period = local.grace_period
  health_check_type         = "ELB"
  max_size                  = 4
  min_size                  = 0
  name                      = "aarch64staging"
  vpc_zone_identifier       = local.subnets

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
        launch_template_id = aws_launch_template.CompilerExplorer-aarch64staging.id
        version            = "$Latest"
      }
      override {
        instance_type = "r7g.medium"
      }
    }
  }

  enabled_metrics = local.common_enabled_metrics

  target_group_arns = [aws_alb_target_group.ce["aarch64staging"].arn]
}

resource "aws_autoscaling_policy" "aarch64staging-mixed" {
  lifecycle {
    create_before_destroy = true
  }

  autoscaling_group_name = aws_autoscaling_group.aarch64staging-mixed.name
  name                   = "aarch64staging-mq-tracker"
  policy_type            = "TargetTrackingScaling"
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
              value = aws_autoscaling_group.aarch64staging-mixed.name
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
