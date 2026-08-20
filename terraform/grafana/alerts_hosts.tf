# Host-level alerts from node_exporter (grafana/agent.yaml).

# Root filesystem running low. /nosym/tmp on CE nodes is a bind mount of /, so
# this is the early warning for the 2048 MiB /healthcheck floor (infra#2310).
# Replaces the hand-made "Instance Disk Space" rule (>90% used for 2m).
# TODO once the 16 GiB node AMI (infra#2312) has rolled: consider tightening to
# an absolute node_filesystem_avail_bytes < 3 GiB so it warns ahead of the
# healthcheck floor; today's 8 GiB fleet sits at ~2.2 GiB so that would fire
# immediately.
resource "grafana_rule_group" "host_disk" {
  name             = "Host Disk"
  folder_uid       = grafana_folder.ce_alerts.uid
  interval_seconds = 60

  rule {
    uid            = "host-root-fs-low"
    name           = "Root filesystem low on free space"
    condition      = "B"
    for            = "10m"
    no_data_state  = "OK"
    exec_err_state = "Error"

    annotations = {
      summary     = "/ has {{ printf \"%.1f\" $values.A.Value }}% free on {{ $labels.agent_hostname }} ({{ $labels.env }})"
      description = "node_filesystem_avail_bytes / node_filesystem_size_bytes for mountpoint=/ has been below 10% for 10 minutes (infra#2310)."
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
        from = 600
        to   = 0
      }
      model = jsonencode({
        refId         = "A"
        datasource    = { type = "prometheus", uid = local.prom_datasource_uid }
        expr          = "100 * node_filesystem_avail_bytes{mountpoint=\"/\"} / node_filesystem_size_bytes{mountpoint=\"/\"}"
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
        conditions    = [{ evaluator = { type = "lt", params = [10] } }]
        intervalMs    = 1000
        maxDataPoints = 43200
      })
    }
  }

  # Conan server data disk. Replaces the hand-made "Conan Disk Space" rule
  # (which had a copy-pasted rule_uid label from the instance rule).
  rule {
    uid            = "conan-fs-low"
    name           = "Conan server disk low on free space"
    condition      = "B"
    for            = "10m"
    no_data_state  = "OK"
    exec_err_state = "Error"

    annotations = {
      summary     = "Conan server disk has {{ printf \"%.1f\" $values.A.Value }}% free"
      description = "/home/ce/.conan_server is below 10% free. See docs/resizing_conan_disk.md in infra for the resize procedure."
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
        from = 600
        to   = 0
      }
      model = jsonencode({
        refId         = "A"
        datasource    = { type = "prometheus", uid = local.prom_datasource_uid }
        expr          = "100 * node_filesystem_avail_bytes{mountpoint=\"/home/ce/.conan_server\"} / node_filesystem_size_bytes{mountpoint=\"/home/ce/.conan_server\"}"
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
        conditions    = [{ evaluator = { type = "lt", params = [10] } }]
        intervalMs    = 1000
        maxDataPoints = 43200
      })
    }
  }
}
