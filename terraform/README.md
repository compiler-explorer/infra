# Terraform

Two roots, each with state on S3:

* `.` -- AWS. Needs AWS credentials (`~/.aws/credentials` or SSO).
* `grafana/` -- Grafana Cloud alerting. Same AWS credentials (the Grafana
  token comes from SSM); see `docs/grafana_terraform.md`.

In either directory:

* `terraform init` -> once, to set up
* `terraform plan` -> previews changes
* `terraform apply` -> applies changes
