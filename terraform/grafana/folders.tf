# Terraform-owned folder; the UI marks its rules "Provisioned". Hand-made
# alerts live in other folders and are not touched by this configuration.
# Existing folders can be adopted with an import block (see
# docs/grafana_terraform.md).
resource "grafana_folder" "ce_alerts" {
  title = "CE Alerts"
  uid   = "ce-alerts"

  prevent_destroy_if_not_empty = true
  lifecycle {
    prevent_destroy = true
  }
}
