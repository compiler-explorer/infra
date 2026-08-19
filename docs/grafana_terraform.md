# Grafana Cloud configuration in Terraform

Part of our Grafana Cloud (`https://ce.grafana.net`) configuration is managed
as code in `terraform/grafana/`. The intent is that the core things -- the
alert rules we rely on, the contact points they notify, the dashboards we would
miss -- live in Terraform and get adopted into it over time, while scratch
dashboards, experiments and one-off alerts made in the UI stay in the UI.
Terraform only ever touches resources declared here; everything else in the
stack is invisible to it.

## What is managed today

- Folder **CE Alerts (terraform-managed)** (`grafana_folder.ce_alerts`) and
  the rule groups in it: "Instance Restarts" (app restarted in place,
  infra#2313) and "Host Disk" (root filesystem low, infra#2310). The folder
  name says who owns it, because provisioned rules are read-only in the UI.

## Adopting existing things

Anything already in Grafana is brought under management with an `import {}`
block plus the matching resource, in one PR; the import block is removed once
applied. Import ids:

- `grafana_folder`: the folder uid (from the `/dashboards/f/<uid>/` URL).
- `grafana_rule_group`: `"<folder uid>:<group name>"`. All rules in the group
  come with it; set each rule's `uid` to the existing one so it is an in-place
  update.
- `grafana_contact_point`: the name, e.g. `"Discord Admins"`. Secure fields
  (webhook URL) come back as `[REDACTED]`, so the HCL must supply the real
  value (read it from SSM with `data "aws_ssm_parameter"`); the first plan
  shows a harmless in-place update of that field, and it then sits in state.
- `grafana_dashboard`: the dashboard uid; keep the JSON in a file and use
  `config_json = file(...)`. Set `store_dashboard_sha256 = true` on the
  provider to keep state small.

`terraform plan` after the import shows what Terraform would change; adjust the
HCL until the only diffs are intended.

Not managed, on purpose:

- The notification policy tree. `grafana_notification_policy` is a singleton
  that takes over the whole tree; rules here use `notification_settings`
  (simplified routing) to name a contact point directly, which bypasses the
  tree. Revisit only if a real routing tree (mute timings, severity routing)
  emerges.
- The node side (`grafana/agent.yaml`), which is already baked into images.

Terraform-created rules carry `provenance: api` and are **read-only in the UI**
(edit and pause are blocked; silences still work and are the right tool during
an incident). That is the intended signal that a rule lives in code. To
experiment, build the rule in a different folder, then promote it by
translating it to HCL -- `GET https://ce.grafana.net/api/v1/provisioning/alert-rules/export?format=hcl`
gives a ready starting point.

## Running it

It is a normal Terraform root with its own state
(`s3://compiler-explorer/terraform/grafana.tfstate`, locked with
`use_lockfile`), so plain `terraform` works:

```
cd terraform/grafana
terraform init
terraform plan
terraform apply
```

or `make grafana-init` / `grafana-plan` / `grafana-apply` from the repo root.
The AWS root (`terraform/`) is unaffected and never needs Grafana credentials.

## Credentials

The provider authenticates with a token for the **`terraform-infra` service
account** on the stack, stored as the SSM SecureString
`/admin/grafanaTerraformToken` and read by a `data "aws_ssm_parameter"` in
`main.tf`. Anyone with AWS credentials can therefore plan and apply; nothing is
written to disk. The token value ends up in `grafana.tfstate` (private,
versioned bucket), the same exposure as the other secrets the AWS state already
holds.

Service account roles (stack UI, Administration > Users and access > Service
accounts): no basic role, plus `fixed:alerting.provisioning:writer` and
`fixed:folders:writer`. Add `fixed:dashboards:writer` only if dashboards are
ever managed here.

Rotation: create a new token on the service account, then
`aws ssm put-parameter --name /admin/grafanaTerraformToken --type SecureString --overwrite --value ...`,
then delete the old token. Nothing in the repo changes.

Because the provider configuration depends on a data source, the legacy
`terraform import ADDR ID` command cannot be used here; use `import {}` blocks
(they go through a normal plan and are reviewable in the PR) and remove them
once applied.

## Adding a rule

Copy the shape of an existing `rule {}`: an instant Prometheus query `A` on
datasource uid `grafanacloud-prom`, a threshold expression `B`, `condition = "B"`,
and `notification_settings { contact_point = local.contact_point_admins }`.
Pick a stable `uid`. If Grafana normalises the `model` JSON and a perpetual
diff appears after apply, paste the `model` from the export endpoint above.
