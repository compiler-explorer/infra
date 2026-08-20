# Alerts about the Compiler Explorer application itself.

# Fires when compiler-explorer.service is restarted in place on a host that was
# already running (infra#2313). A freshly launched instance is a new time
# series whose start time never changes, so scale-outs and replacements do not
# trigger this; only a same-host restart does. All environments on purpose: an
# unexpected staging restart is as interesting as a prod one.
resource "grafana_rule_group" "instance_restarts" {
  name             = "Instance Restarts"
  folder_uid       = grafana_folder.ce_alerts.uid
  interval_seconds = 60

  rule {
    uid            = "ce-restart-detected"
    name           = "Compiler Explorer restart detected"
    condition      = "B"
    for            = "1m"
    no_data_state  = "OK"
    exec_err_state = "Error"

    annotations = {
      summary     = "CE app restarted on {{ $labels.agent_hostname }} ({{ $labels.env }})"
      description = "process_start_time_seconds changed in the last 15m, i.e. systemd restarted compiler-explorer.service in place (infra#2313). Check Papertrail host:{{ $labels.agent_hostname }} or journalctl -u compiler-explorer on the host. New instances booting do not trigger this; only same-host restarts do."
    }
    labels = {
      severity = "warning"
    }

    notification_settings {
      contact_point = local.contact_point_admins
    }

    data {
      ref_id         = "A"
      query_type     = "instant"
      datasource_uid = local.prom_datasource_uid
      relative_time_range {
        from = 900
        to   = 0
      }
      model = jsonencode({
        refId         = "A"
        datasource    = { type = "prometheus", uid = local.prom_datasource_uid }
        expr          = "changes(process_start_time_seconds{job=\"compiler_explorer\"}[15m])"
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
