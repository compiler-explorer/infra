# Plots the arrival-rate scaling metric exactly as the ASG target-tracking policies compute it
# (../prod-blue-green.tf, ../beta-blue-green.tf), so the graph and the scaler agree.
locals {
  cloudwatch_datasource = { type = "cloudwatch", uid = "0sq-lf5Gz" }
  queue_scaling_colours = ["blue", "green"]
  # target mirrors target_value on each environment's arrival-rate policy.
  queue_scaling_envs = [
    { name = "prod", title = "Prod", target = 25 },
    { name = "beta", title = "Beta", target = 20 },
  ]
  queue_scaling_env_colours = {
    for pair in setproduct(local.queue_scaling_envs, local.queue_scaling_colours) :
    "${pair[0].name}-${pair[1]}" => { env = pair[0], colour = pair[1] }
  }
  queue_scaling_panel_height = 9
  queue_scaling_row_height   = local.queue_scaling_panel_height + 1

  queue_scaling_sent_queries = {
    for key, ec in local.queue_scaling_env_colours : key => {
      datasource       = local.cloudwatch_datasource
      refId            = "sent_${ec.colour}"
      id               = "sent_${ec.colour}"
      region           = "default"
      namespace        = "AWS/SQS"
      metricName       = "NumberOfMessagesSent"
      dimensions       = { QueueName = "${ec.env.name}-compilation-queue-${ec.colour}.fifo" }
      statistic        = "Sum"
      period           = "60"
      matchExact       = true
      queryMode        = "Metrics"
      metricQueryType  = 0
      metricEditorMode = 0
      label            = ec.colour
    }
  }
  queue_scaling_healthy_queries = {
    for key, ec in local.queue_scaling_env_colours : key => {
      datasource = local.cloudwatch_datasource
      refId      = "healthy_${ec.colour}"
      id         = "healthy_${ec.colour}"
      region     = "default"
      namespace  = "AWS/ApplicationELB"
      metricName = "HealthyHostCount"
      dimensions = {
        LoadBalancer = data.aws_lb.compilation.arn_suffix
        TargetGroup  = data.aws_lb_target_group.compilation[key].arn_suffix
      }
      # Every AZ reports the full count, so Maximum rather than Sum (as in the policy).
      statistic        = "Maximum"
      period           = "60"
      matchExact       = true
      queryMode        = "Metrics"
      metricQueryType  = 0
      metricEditorMode = 0
      label            = ec.colour
    }
  }
  queue_scaling_per_instance_queries = {
    for key, ec in local.queue_scaling_env_colours : key => {
      datasource = local.cloudwatch_datasource
      refId      = "per_instance_${ec.colour}"
      id         = "per_instance_${ec.colour}"
      region     = "default"
      expression = "IF(healthy_${ec.colour} > 0, sent_${ec.colour} / healthy_${ec.colour}, sent_${ec.colour})"
      # The CloudWatch plugin errors on an expression query missing these, empty or not.
      namespace        = ""
      metricName       = ""
      dimensions       = {}
      statistic        = "Average"
      matchExact       = true
      period           = "60"
      queryMode        = "Metrics"
      metricQueryType  = 0
      metricEditorMode = 1
      label            = ec.colour
    }
  }

  queue_scaling_colour_overrides = [
    for colour in local.queue_scaling_colours : {
      matcher    = { id = "byName", options = colour }
      properties = [{ id = "color", value = { mode = "fixed", fixedColor = colour } }]
    }
  ]
  # The plugin returns hidden inputs of a math expression anyway.
  queue_scaling_hidden_input_overrides = [
    for ref in flatten([for colour in local.queue_scaling_colours : ["sent_${colour}", "healthy_${colour}"]]) : {
      matcher    = { id = "byFrameRefID", options = ref }
      properties = [{ id = "custom.hideFrom", value = { legend = true, tooltip = true, viz = true } }]
    }
  ]
  queue_scaling_timeseries_defaults = {
    type       = "timeseries"
    datasource = local.cloudwatch_datasource
    options = {
      legend  = { displayMode = "list", placement = "bottom", showLegend = true }
      tooltip = { mode = "multi", sort = "none" }
    }
  }

  queue_scaling_panels = flatten([
    for i, env in local.queue_scaling_envs : [
      {
        type      = "row"
        title     = env.title
        collapsed = false
        gridPos   = { h = 1, w = 24, x = 0, y = i * local.queue_scaling_row_height }
        panels    = []
      },
      merge(local.queue_scaling_timeseries_defaults, {
        title       = "Arrivals per minute per healthy instance (target ${env.target})"
        description = "The metric ${env.name}'s arrival-rate policy tracks: NumberOfMessagesSent on the colour's queue divided by its healthy target count, or the raw arrival rate when the colour has none. The ASG scales out while this sits above the dashed line."
        gridPos     = { h = local.queue_scaling_panel_height, w = 8, x = 0, y = i * local.queue_scaling_row_height + 1 }
        targets = flatten([
          for colour in local.queue_scaling_colours : [
            merge(local.queue_scaling_sent_queries["${env.name}-${colour}"], { hide = true }),
            merge(local.queue_scaling_healthy_queries["${env.name}-${colour}"], { hide = true }),
            local.queue_scaling_per_instance_queries["${env.name}-${colour}"],
          ]
        ])
        fieldConfig = {
          defaults = {
            min    = 0
            unit   = "short"
            custom = { thresholdsStyle = { mode = "dashed" } }
            thresholds = {
              mode = "absolute"
              steps = [
                { color = "transparent", value = null },
                { color = "red", value = env.target },
              ]
            }
          }
          overrides = concat(local.queue_scaling_colour_overrides, local.queue_scaling_hidden_input_overrides)
        }
      }),
      merge(local.queue_scaling_timeseries_defaults, {
        title       = "Messages sent per minute"
        description = "NumberOfMessagesSent (Sum, 60s) on ${env.name}-compilation-queue-{blue,green}.fifo."
        gridPos     = { h = local.queue_scaling_panel_height, w = 8, x = 8, y = i * local.queue_scaling_row_height + 1 }
        targets     = [for colour in local.queue_scaling_colours : local.queue_scaling_sent_queries["${env.name}-${colour}"]]
        fieldConfig = {
          defaults  = { min = 0, unit = "short" }
          overrides = local.queue_scaling_colour_overrides
        }
      }),
      merge(local.queue_scaling_timeseries_defaults, {
        title       = "Healthy instances"
        description = "HealthyHostCount (Maximum) per colour's target group; the divisor of the scaling metric."
        gridPos     = { h = local.queue_scaling_panel_height, w = 8, x = 16, y = i * local.queue_scaling_row_height + 1 }
        targets     = [for colour in local.queue_scaling_colours : local.queue_scaling_healthy_queries["${env.name}-${colour}"]]
        fieldConfig = {
          defaults = {
            min      = 0
            decimals = 0
            unit     = "short"
            custom   = { lineInterpolation = "stepAfter" }
          }
          overrides = local.queue_scaling_colour_overrides
        }
      }),
    ]
  ])
}

resource "grafana_dashboard" "queue_scaling" {
  config_json = jsonencode({
    uid           = "ce-queue-scaling"
    title         = "Queue Scaling"
    tags          = ["autoscaling", "sqs"]
    timezone      = "utc"
    refresh       = "1m"
    schemaVersion = 39
    time          = { from = "now-24h", to = "now" }
    panels = [
      for i, panel in local.queue_scaling_panels : merge(panel, { id = i + 1 })
    ]
  })
}

data "aws_lb" "compilation" {
  name = "GccExplorerApp"
}

data "aws_lb_target_group" "compilation" {
  for_each = local.queue_scaling_env_colours
  name     = "${title(each.value.env.name)}-${title(each.value.colour)}"
}
