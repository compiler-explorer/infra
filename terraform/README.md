# Terraform

Two roots, each with state on S3:

* `.` -- AWS. Needs AWS credentials (`~/.aws/credentials` or SSO).
* `grafana/` -- Grafana Cloud alerting. Same AWS credentials (the Grafana
  token comes from SSM); see `docs/grafana_terraform.md`.

In either directory:

* `terraform init` -> once, to set up
* `terraform plan` -> previews changes
* `terraform apply` -> applies changes

## Variables that change behaviour

* `prod_queue_scaling` (default `true`) -- scales prod's compilation fleet on SQS queue
  metrics instead of CPU. `true` gives the queue policies and no cpu-tracker; `false` gives the
  reverse, and is the revert. The commands are in `docs/ce-router-cutover-checklist.md`,
  sections H2 and I.
