# Terraform-owned folder; the name says so because provisioned rules are
# read-only in the UI. Hand-made alerts live in other folders and are not
# touched by this configuration. Existing folders can be adopted with an
# import block (see docs/grafana_terraform.md).
resource "grafana_folder" "ce_alerts" {
  title = "CE Alerts (terraform-managed)"
  uid   = "ce-alerts"

  prevent_destroy_if_not_empty = true
  lifecycle {
    prevent_destroy = true
  }
}
