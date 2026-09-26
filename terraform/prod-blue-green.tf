variable "prod_queue_scaling" {
  description = <<-EOT
    Scale prod's compilation fleet on SQS queue metrics instead of CPU.

    false (the default, and the state to return to): the module's cpu-tracker policy runs and
    the queue policies below do not exist. true: the reverse.

    Flipping this is the whole switch, and the whole revert. Both directions are one targeted
    apply; see docs/ce-router-cutover-checklist.md for the commands. Nothing else needs to
    change, and neither direction moves desired capacity on its own - removing a target
    tracking policy leaves the fleet where it is and simply stops adjusting it, so the switch
    is a change of control loop rather than a change of size.
  EOT
  type        = bool
  default     = false
}

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
  launch_template_id        = aws_launch_template.ce["prod"].id
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

  # CPU tracking, and the thing the queue-depth and arrival-rate policies below replace. The
  # two are mutually exclusive by design: prod serves almost no web traffic - static content is
  # on S3 behind CloudFront and the rest is cached - so once compilation goes through SQS, CPU
  # is measuring the same work the queue metrics measure, only later.
  enable_autoscaling_policy = !var.prod_queue_scaling
  autoscaling_target_cpu    = 25.0
}

# Queue-based scaling for prod, replacing CPU tracking. Present only when prod_queue_scaling is
# true; the module's cpu-tracker policy is present only when it is false.
#
# Targets come from replaying Friday 2026-09-25's real prod traffic (mean 149 compiles/min,
# peak 473) through both policies: a rate target of 20 gives a mean fleet of 9.8 against the
# 9.7 prod actually ran that day, peaks at 24 against an actual 18, and drops nothing, on that
# day or against a synthetic five-fold twenty-minute spike. The same settings were then run
# against real load on beta, where they scaled 1 -> 5 exactly as predicted.
resource "aws_autoscaling_policy" "prod_blue_compilation_scaling" {
  count = var.prod_queue_scaling ? 1 : 0
  lifecycle {
    create_before_destroy = true
  }

  autoscaling_group_name = module.prod_blue_green.blue_asg_name
  name                   = "prod-compilation-queue-tracker-blue"
  policy_type            = "TargetTrackingScaling"
  # An instance is not serving until the ASG calls it healthy at health_check_grace_period, so
  # counting it sooner flatters every per-instance figure. Matches the module's CPU policy.
  estimated_instance_warmup = local.grace_period + 30

  target_tracking_configuration {
    # A backlog worth roughly fifteen seconds of one instance's work. At 2 this policy was
    # wildly overeager - replaying a real Friday through it asked for 40 instances for a peak
    # needing four, because two messages per instance is about a second of work and any blip
    # cleared it. Its job is to be the safety net the arrival-rate policy falls back on, not to
    # set the fleet size.
    target_value = 15
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
              value = module.prod_blue_green.sqs_queue_blue_name
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
        label = "Instances that can actually take work, which is not the same as InService: an instance joins the group about forty seconds after launch but cannot serve until the application is up, roughly four minutes later. Counting those flatters the metric during exactly the window when the backlog is growing."
        id    = "m2"
        metric_stat {
          metric {
            namespace   = "AWS/ApplicationELB"
            metric_name = "HealthyHostCount"
            dimensions {
              name  = "LoadBalancer"
              value = aws_alb.GccExplorerApp.arn_suffix
            }
            dimensions {
              name  = "TargetGroup"
              value = module.prod_blue_green.target_group_arn_suffixes["blue"]
            }
          }
          # Every availability zone reports the full target count, so Sum multiplies by the
          # number of zones - it read 25 for a five-instance fleet. Maximum is the true count
          # and tolerates a zone publishing late.
          stat = "Maximum"
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

resource "aws_autoscaling_policy" "prod_green_compilation_scaling" {
  count = var.prod_queue_scaling ? 1 : 0
  lifecycle {
    create_before_destroy = true
  }

  autoscaling_group_name = module.prod_blue_green.green_asg_name
  name                   = "prod-compilation-queue-tracker-green"
  policy_type            = "TargetTrackingScaling"
  # An instance is not serving until the ASG calls it healthy at health_check_grace_period, so
  # counting it sooner flatters every per-instance figure. Matches the module's CPU policy.
  estimated_instance_warmup = local.grace_period + 30

  target_tracking_configuration {
    # A backlog worth roughly fifteen seconds of one instance's work. At 2 this policy was
    # wildly overeager - replaying a real Friday through it asked for 40 instances for a peak
    # needing four, because two messages per instance is about a second of work and any blip
    # cleared it. Its job is to be the safety net the arrival-rate policy falls back on, not to
    # set the fleet size.
    target_value = 15
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
              value = module.prod_blue_green.sqs_queue_green_name
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
        label = "Instances that can actually take work, which is not the same as InService: an instance joins the group about forty seconds after launch but cannot serve until the application is up, roughly four minutes later. Counting those flatters the metric during exactly the window when the backlog is growing."
        id    = "m2"
        metric_stat {
          metric {
            namespace   = "AWS/ApplicationELB"
            metric_name = "HealthyHostCount"
            dimensions {
              name  = "LoadBalancer"
              value = aws_alb.GccExplorerApp.arn_suffix
            }
            dimensions {
              name  = "TargetGroup"
              value = module.prod_blue_green.target_group_arn_suffixes["green"]
            }
          }
          # Every availability zone reports the full target count, so Sum multiplies by the
          # number of zones - it read 25 for a five-instance fleet. Maximum is the true count
          # and tolerates a zone publishing late.
          stat = "Maximum"
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

resource "aws_autoscaling_policy" "prod_blue_arrival_rate_scaling" {
  count = var.prod_queue_scaling ? 1 : 0
  lifecycle {
    create_before_destroy = true
  }

  autoscaling_group_name = module.prod_blue_green.blue_asg_name
  name                   = "prod-arrival-rate-tracker-blue"
  policy_type            = "TargetTrackingScaling"

  # Matches the convention the module's CPU policy uses, rather than the 90 the depth policy
  # sets: an instance is not serving until the ASG calls it healthy at health_check_grace_period
  # (240s here), and counting it sooner makes arrivals-per-instance look better than it is.
  estimated_instance_warmup = local.grace_period + 30

  target_tracking_configuration {
    # Messages a minute one instance should absorb. Derived by replaying a real day of prod
    # traffic (mean 149/min, peak 473/min) through this policy: at 20 the fleet averages 10.2
    # instances against the 9.7 prod actually ran on CPU tracking that day, peaks at 24, and
    # drops nothing - including against a synthetic 5x twenty-minute spike. Hotter settings
    # start losing requests: 25 drops 0.26% of that spike, 30 drops 0.53%.
    #
    # The earlier figure of 60 came from a beta instance saturating at ~120/min on synthetic
    # payloads, which is neither prod's workload (p50 0.56s but p99 17.3s) nor a rate anything
    # should sit at. Recalibrate against measurements, not against saturation.
    target_value = 20

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
              value = module.prod_blue_green.sqs_queue_blue_name
            }
          }
          # A count over the period, so Sum is the right statistic here - unlike
          # ApproximateNumberOfMessagesVisible, which is a gauge and wants Maximum.
          stat = "Sum"
        }
        return_data = false
      }
      metrics {
        label = "Instances that can actually take work, which is not the same as InService: an instance joins the group about forty seconds after launch but cannot serve until the application is up, roughly four minutes later. Counting those flatters the metric during exactly the window when the backlog is growing."
        id    = "a2"
        metric_stat {
          metric {
            namespace   = "AWS/ApplicationELB"
            metric_name = "HealthyHostCount"
            dimensions {
              name  = "LoadBalancer"
              value = aws_alb.GccExplorerApp.arn_suffix
            }
            dimensions {
              name  = "TargetGroup"
              value = module.prod_blue_green.target_group_arn_suffixes["blue"]
            }
          }
          # Every availability zone reports the full target count, so Sum multiplies by the
          # number of zones - it read 25 for a five-instance fleet. Maximum is the true count
          # and tolerates a zone publishing late.
          stat = "Maximum"
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

resource "aws_autoscaling_policy" "prod_green_arrival_rate_scaling" {
  count = var.prod_queue_scaling ? 1 : 0
  lifecycle {
    create_before_destroy = true
  }

  autoscaling_group_name    = module.prod_blue_green.green_asg_name
  name                      = "prod-arrival-rate-tracker-green"
  policy_type               = "TargetTrackingScaling"
  estimated_instance_warmup = local.grace_period + 30

  target_tracking_configuration {
    target_value = 20

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
              value = module.prod_blue_green.sqs_queue_green_name
            }
          }
          stat = "Sum"
        }
        return_data = false
      }
      metrics {
        label = "Instances that can actually take work, which is not the same as InService: an instance joins the group about forty seconds after launch but cannot serve until the application is up, roughly four minutes later. Counting those flatters the metric during exactly the window when the backlog is growing."
        id    = "a2"
        metric_stat {
          metric {
            namespace   = "AWS/ApplicationELB"
            metric_name = "HealthyHostCount"
            dimensions {
              name  = "LoadBalancer"
              value = aws_alb.GccExplorerApp.arn_suffix
            }
            dimensions {
              name  = "TargetGroup"
              value = module.prod_blue_green.target_group_arn_suffixes["green"]
            }
          }
          # Every availability zone reports the full target count, so Sum multiplies by the
          # number of zones - it read 25 for a five-instance fleet. Maximum is the true count
          # and tolerates a zone publishing late.
          stat = "Maximum"
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
