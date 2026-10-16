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
    tags          = ["autoscaling", "sqs", "terraform"]
    editable      = false
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

locals {
  public_envs = "prod|gpu|winprod"
  # Direct and queue-worker requests increment different counters, so totals need all of them.
  public_compile_counters = [
    "ce_compilations_total",
    "ce_sqs_compilations_total",
    "ce_project_build_compilations_total",
    "ce_sqs_project_build_compilations_total",
  ]
  public_execute_counters = [
    "ce_executions_total",
    "ce_sqs_executions_total",
    "ce_project_build_executions_total",
    "ce_sqs_project_build_executions_total",
  ]
  # rate/increase drop __name__, so each counter is relabelled to keep `or` from discarding one.
  public_counter_sums = {
    for name, q in {
      compiles_6m         = { counters = local.public_compile_counters, fn = "increase", range = "360s", filter = "" }
      compiles_1w         = { counters = local.public_compile_counters, fn = "increase", range = "1w", filter = "" }
      compiles_30d        = { counters = local.public_compile_counters, fn = "increase", range = "30d", filter = "" }
      compiles_rate       = { counters = local.public_compile_counters, fn = "rate", range = "$__rate_interval", filter = "" }
      compiles_rate_not_c = { counters = local.public_compile_counters, fn = "rate", range = "$__rate_interval", filter = ", language!~\"c(\\\\+\\\\+)?\"" }
      executions_6m       = { counters = local.public_execute_counters, fn = "increase", range = "360s", filter = "" }
      executions_rate     = { counters = local.public_execute_counters, fn = "rate", range = "$__rate_interval", filter = "" }
      } : name => join(" or ", [
        for c in q.counters : "label_replace(${q.fn}(${c}{env=~\"${local.public_envs}\"${q.filter}}[${q.range}]), \"counter\", \"${c}\", \"\", \"\")"
    ])
  }
  public_exprs = {
    compiles_per_sec                   = "sum(${local.public_counter_sums.compiles_6m}) / 360"
    executions_per_sec                 = "sum(${local.public_counter_sums.executions_6m}) / 360"
    million_compiles_per_month         = "sum(${local.public_counter_sums.compiles_30d}) / 1000000"
    compiles_last_week_by_language     = "sum by (language) (${local.public_counter_sums.compiles_1w})"
    compiles_last_week_top20           = "topk(20, sum by (language) (${local.public_counter_sums.compiles_1w}))"
    compiles_last_week_rest            = "sum(${local.public_counter_sums.compiles_1w}) - sum(topk(20, sum by (language) (${local.public_counter_sums.compiles_1w})))"
    compiles_per_min_by_language       = "sum by (language) (${local.public_counter_sums.compiles_rate}) * 60"
    compiles_per_min_by_language_not_c = "sum by (language) (${local.public_counter_sums.compiles_rate_not_c}) * 60"
    executions_per_min_by_language     = "sum by (language) (${local.public_counter_sums.executions_rate}) * 60"
  }
}

# Public stats page; stats.compiler-explorer.com redirects to its public share (../alb.tf).
resource "grafana_dashboard" "public" {
  config_json = templatefile("${path.module}/dashboards/public.json.tftpl", { expr = local.public_exprs })
}

resource "grafana_dashboard_public" "public" {
  dashboard_uid          = grafana_dashboard.public.uid
  uid                    = "FVXir_z4z"
  access_token           = "326d9aa2606b4efea25f4458a4c3f065"
  is_enabled             = true
  share                  = "public"
  time_selection_enabled = false
  annotations_enabled    = false
}
