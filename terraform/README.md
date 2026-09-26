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

* `prod_queue_scaling` (default `false`) -- scales prod's compilation fleet on SQS queue
  metrics instead of CPU. `false` gives the cpu-tracker policy and no queue policies; `true`
  gives the reverse. Switching and reverting are the same targeted apply with and without
  `-var 'prod_queue_scaling=true'`; the commands are in
  `docs/ce-router-cutover-checklist.md`, sections H2 and I.

  If prod is running with this on, the flip belongs in a commit. Left uncommitted, the next
  plan anyone runs reverts it without saying so.
