# Blue-Green deployment infrastructure for Beta environment
# Uses the blue_green module to create matching blue and green infrastructure

module "beta_blue_green" {
  source = "./modules/blue_green"

  environment               = "beta"
  vpc_id                    = module.ce_network.vpc.id
  launch_template_id        = aws_launch_template.ce["beta"].id
  subnets                   = local.subnets
  asg_max_size              = 10 # Increased to 10 for high load scenarios
  initial_desired_capacity  = 0
  health_check_grace_period = local.grace_period
  default_cooldown          = 90 # Reduced from 3min to 1.5min
  enabled_metrics           = local.common_enabled_metrics
  initial_active_color      = "blue"

  # Disable default auto-scaling policy - we'll use custom SQS-based scaling
  enable_autoscaling_policy = false
}

# Custom auto-scaling policies for Beta environment based on compilation queue depth

resource "aws_autoscaling_policy" "beta_blue_compilation_scaling" {
  lifecycle {
    create_before_destroy = true
  }

  autoscaling_group_name = module.beta_blue_green.blue_asg_name
  name                   = "beta-compilation-queue-tracker-blue"
  policy_type            = "TargetTrackingScaling"
  # An instance is not serving until the ASG calls it healthy at health_check_grace_period, so
  # counting it sooner flatters every per-instance figure. Matches the module's CPU policy.
  estimated_instance_warmup = local.grace_period + 30

  target_tracking_configuration {
    target_value = 2 # Reduced to 2 messages per instance for aggressive scaling
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
              value = module.beta_blue_green.sqs_queue_blue_name
            }
          }
          # A gauge - the depth at a moment - so Maximum is the statistic that means something.
          # Sum happens to agree while SQS emits one datapoint per period, and would quietly
          # stop agreeing if the period changed.
          stat = "Maximum"
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
        label       = "Backlog per instance, or the raw backlog when this colour has none yet"
        id          = "e1"
        expression  = "IF(m2 > 0, (m1 + 1) / m2, m1 + 1)"
        return_data = true
      }
    }
  }
}

resource "aws_autoscaling_policy" "beta_green_compilation_scaling" {
  lifecycle {
    create_before_destroy = true
  }

  autoscaling_group_name = module.beta_blue_green.green_asg_name
  name                   = "beta-compilation-queue-tracker-green"
  policy_type            = "TargetTrackingScaling"
  # An instance is not serving until the ASG calls it healthy at health_check_grace_period, so
  # counting it sooner flatters every per-instance figure. Matches the module's CPU policy.
  estimated_instance_warmup = local.grace_period + 30

  target_tracking_configuration {
    target_value = 2 # Reduced to 2 messages per instance for aggressive scaling
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
              value = module.beta_blue_green.sqs_queue_green_name
            }
          }
          # A gauge - the depth at a moment - so Maximum is the statistic that means something.
          # Sum happens to agree while SQS emits one datapoint per period, and would quietly
          # stop agreeing if the period changed.
          stat = "Maximum"
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
        label       = "Backlog per instance, or the raw backlog when this colour has none yet"
        id          = "e1"
        expression  = "IF(m2 > 0, (m1 + 1) / m2, m1 + 1)"
        return_data = true
      }
    }
  }
}

# Arrival-rate scaling, running alongside the queue-depth policies above. An ASG with several
# active target-tracking policies follows whichever asks for the most capacity, so the two
# compose rather than compete.
#
# Why a second policy rather than a change to the first: queue depth is the integral of
# (arrivals - departures), so it only rises once the fleet is already behind, and it reports
# debt already incurred. The rate at which messages arrive is the forward-looking signal - it
# sizes the fleet to demand rather than to backlog. An ASG with several active target-tracking
# policies follows whichever asks for the most capacity, so the two compose without conflict:
# this one leads, and the depth policy corrects whatever it under-provisions.
#
# The trade-off is calibration. Depth-based scaling needs no constant - it self-corrects
# whatever a single instance happens to manage, which moves with the payload mix (measured
# 2 compiles/s on small sources, 1.26/s on heavy ones). Rate-based scaling needs a number for
# "messages a minute one instance absorbs", and that number is workload- and
# instance-type-specific. Hence keeping both.

resource "aws_autoscaling_policy" "beta_blue_arrival_rate_scaling" {
  lifecycle {
    create_before_destroy = true
  }

  autoscaling_group_name = module.beta_blue_green.blue_asg_name
  name                   = "beta-arrival-rate-tracker-blue"
  policy_type            = "TargetTrackingScaling"

  # Matches the convention the module's CPU policy uses, rather than the 90 the depth policy
  # sets: an instance is not serving until the ASG calls it healthy at health_check_grace_period
  # (240s here), and counting it sooner makes arrivals-per-instance look better than it is.
  estimated_instance_warmup = local.grace_period + 30

  target_tracking_configuration {
    # Messages a minute one instance should absorb. A beta m5.large saturates around 120/min;
    # 60 therefore runs at about half capacity, so a spike has somewhere to land while new
    # instances boot. Raise it to run hotter, lower it for more headroom.
    #
    # CALIBRATE PER ENVIRONMENT. Prod serves web traffic from the same instances, so its
    # spare capacity for compilation is not beta's.
    target_value = 60

    customized_metric_specification {
      metrics {
        label = "Messages arriving on this colour's compilation queue each minute"
        id    = "a1"
        metric_stat {
          metric {
            namespace   = "AWS/SQS"
            metric_name = "NumberOfMessagesSent"
            dimensions {
              name  = "QueueName"
              value = module.beta_blue_green.sqs_queue_blue_name
            }
          }
          # A count over the period, so Sum is the right statistic here - unlike
          # ApproximateNumberOfMessagesVisible, which is a gauge and wants Maximum.
          stat = "Sum"
        }
        return_data = false
      }
      metrics {
        label = "Instances in service"
        id    = "a2"
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
        label = "Arrivals per minute per instance, or the raw arrival rate when this colour has none"
        id    = "e1"
        # The a2 = 0 case keeps the metric defined so a colour at zero instances can still be
        # woken by traffic; with instances present it is plain arrivals per instance.
        expression  = "IF(a2 > 0, a1 / a2, a1)"
        return_data = true
      }
    }
  }
}

resource "aws_autoscaling_policy" "beta_green_arrival_rate_scaling" {
  lifecycle {
    create_before_destroy = true
  }

  autoscaling_group_name    = module.beta_blue_green.green_asg_name
  name                      = "beta-arrival-rate-tracker-green"
  policy_type               = "TargetTrackingScaling"
  estimated_instance_warmup = local.grace_period + 30

  target_tracking_configuration {
    target_value = 60

    customized_metric_specification {
      metrics {
        label = "Messages arriving on this colour's compilation queue each minute"
        id    = "a1"
        metric_stat {
          metric {
            metric_name = "NumberOfMessagesSent"
            namespace   = "AWS/SQS"
            dimensions {
              name  = "QueueName"
              value = module.beta_blue_green.sqs_queue_green_name
            }
          }
          stat = "Sum"
        }
        return_data = false
      }
      metrics {
        label = "Instances in service"
        id    = "a2"
        metric_stat {
          metric {
            metric_name = "GroupInServiceInstances"
            namespace   = "AWS/AutoScaling"
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
        label       = "Arrivals per minute per instance, or the raw arrival rate when this colour has none"
        id          = "e1"
        expression  = "IF(a2 > 0, a1 / a2, a1)"
        return_data = true
      }
    }
  }
}
