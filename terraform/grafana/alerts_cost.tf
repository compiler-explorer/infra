# Cost-control alerts.

# Staging environments cost money while up and are usually only needed around
# a deploy. Replaces the hand-made "Staging instances alert" (uid o0kBVyX4k,
# folder "General Alerting"), which counted CPUs with env=staging and so fired
# forever once ce-router-staging (a 24/7 t4g.medium tagged env=staging) came
# along. Counting CE app processes instead sees only real staging nodes; the
# router does not run the app.
resource "grafana_rule_group" "staging_instances" {
  name             = "Staging Instances"
  folder_uid       = grafana_folder.ce_alerts.uid
  interval_seconds = 3600

  rule {
    uid            = "staging-instances-up"
    name           = "Staging instances left running"
    condition      = "B"
    for            = "2h"
    no_data_state  = "OK"
    exec_err_state = "Error"

    annotations = {
      summary     = "Staging has had {{ printf \"%.0f\" $values.A.Value }} CE node(s) up for over 2 hours"
      description = "Instances with env=staging have been running for a while; if nobody is mid-deploy they should be shut down (ce --env staging environment stop)."
    }
    labels = {
      severity = "info"
    }

    notification_settings {
      contact_point = local.contact_point_admins
    }

    data {
      ref_id         = "A"
      query_type     = "instant"
      datasource_uid = local.prom_datasource_uid
      relative_time_range {
        from = 600
        to   = 0
      }
      model = jsonencode({
        refId         = "A"
        datasource    = { type = "prometheus", uid = local.prom_datasource_uid }
        expr          = "count(process_start_time_seconds{job=\"compiler_explorer\", env=\"staging\"})"
        instant       = true
        range         = false
        intervalMs    = 1000
        maxDataPoints = 43200
      })
    }
    data {
      ref_id         = "B"
      datasource_uid = "__expr__"
      relative_time_range {
        from = 0
        to   = 0
      }
      model = jsonencode({
        refId         = "B"
        type          = "threshold"
        datasource    = { type = "__expr__", uid = "__expr__" }
        expression    = "A"
        conditions    = [{ evaluator = { type = "gt", params = [0] } }]
        intervalMs    = 1000
        maxDataPoints = 43200
      })
    }
  }
}
