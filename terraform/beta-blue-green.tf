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

  # Disable default auto-scaling policy - we'll use custom SQS-based scaling
  enable_autoscaling_policy = false
}

# Custom auto-scaling policies for Beta environment based on compilation queue depth
# Scales based on messages in the beta-compilation-queue.fifo, target: 3 compilations per instance

resource "aws_autoscaling_policy" "beta_blue_compilation_scaling" {
  lifecycle {
    create_before_destroy = true
  }

  autoscaling_group_name    = module.beta_blue_green.blue_asg_name
  name                      = "beta-compilation-queue-tracker-blue"
  policy_type               = "TargetTrackingScaling"
  estimated_instance_warmup = local.cooldown

  target_tracking_configuration {
    target_value = 3
    customized_metric_specification {
      metrics {
        label = "Get the queue size (the number of compilation messages waiting to be processed)"
        id    = "m1"
        metric_stat {
          metric {
            namespace   = "AWS/SQS"
            metric_name = "ApproximateNumberOfMessagesVisible"
            dimensions {
              name  = "QueueName"
              value = module.compilation_lambda_beta.sqs_queue_name
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
              value = module.beta_blue_green.blue_asg_name
            }
          }
          stat = "Average"
        }
        return_data = false
      }
      metrics {
        label = "Get blue target group connection count (to check if this ASG is active)"
        id    = "m3"
        metric_stat {
          metric {
            namespace   = "AWS/ApplicationELB"
            metric_name = "ActiveConnectionCount"
            dimensions {
              name  = "TargetGroup"
              value = module.beta_blue_green.blue_target_group_arn
            }
          }
          stat = "Average"
        }
        return_data = false
      }
      metrics {
        label       = "Calculate backlog per instance, but only scale if this ASG is receiving traffic"
        id          = "e1"
        expression  = "IF(m3 > 0 OR m2 > 0, IF(m2 > 0, (m1 + 1) / m2, m1 + 1), 0)"
        return_data = true
      }
    }
  }
}

resource "aws_autoscaling_policy" "beta_green_compilation_scaling" {
  lifecycle {
    create_before_destroy = true
  }

  autoscaling_group_name    = module.beta_blue_green.green_asg_name
  name                      = "beta-compilation-queue-tracker-green"
  policy_type               = "TargetTrackingScaling"
  estimated_instance_warmup = local.cooldown

  target_tracking_configuration {
    target_value = 3
    customized_metric_specification {
      metrics {
        label = "Get the queue size (the number of compilation messages waiting to be processed)"
        id    = "m1"
        metric_stat {
          metric {
            namespace   = "AWS/SQS"
            metric_name = "ApproximateNumberOfMessagesVisible"
            dimensions {
              name  = "QueueName"
              value = module.compilation_lambda_beta.sqs_queue_name
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
              value = module.beta_blue_green.green_asg_name
            }
          }
          stat = "Average"
        }
        return_data = false
      }
      metrics {
        label = "Get green target group connection count (to check if this ASG is active)"
        id    = "m3"
        metric_stat {
          metric {
            namespace   = "AWS/ApplicationELB"
            metric_name = "ActiveConnectionCount"
            dimensions {
              name  = "TargetGroup"
              value = module.beta_blue_green.green_target_group_arn
            }
          }
          stat = "Average"
        }
        return_data = false
      }
      metrics {
        label       = "Calculate backlog per instance, but only scale if this ASG is receiving traffic"
        id          = "e1"
        expression  = "IF(m3 > 0 OR m2 > 0, IF(m2 > 0, (m1 + 1) / m2, m1 + 1), 0)"
        return_data = true
      }
    }
  }
}
