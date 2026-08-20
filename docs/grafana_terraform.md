# Grafana Cloud configuration in Terraform

Part of our Grafana Cloud (`https://ce.grafana.net`) configuration is managed
as code in `terraform/grafana/`. The intent is that the core things -- the
alert rules we rely on, the contact points they notify, the dashboards we would
miss -- live in Terraform and get adopted into it over time, while scratch
dashboards, experiments and one-off alerts made in the UI stay in the UI.
Terraform only ever touches resources declared here; everything else in the
stack is invisible to it.

## What is managed today

- Folder **CE Alerts** (`grafana_folder.ce_alerts`) and the rule groups in it:
  "Instance Restarts" (app restarted in place, infra#2313) and "Host Disk"
  (root filesystem and conan server disk low, infra#2310). The UI marks these
  rules "Provisioned", which is how you can tell they live here.

All other alert rules have been adopted or replaced: the legacy hand-made
"Instance Disk Space" and "Conan Disk Space" rules were recreated here (with
fixed labels and real annotations) and the originals deleted. The remaining
`ProbeFailedExecutionsTooHigh` rule belongs to the Synthetic Monitoring app,
which owns and regenerates it -- leave it alone.

Contact points ("Discord Admins", "Discord Admins Microsoft", "Mail MS") are
still hand-made; rules reference "Discord Admins" by name. Adopting them is
the natural next step but puts the webhook URLs in state (see below).

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

The service account (stack UI, Administration > Users and access > Service
accounts) has basic role **Editor**: it covers folders, alert rules and
dashboards in one go, so adopting more objects later needs no permission
changes. Roles attach to the service account, not the token, so they can be
adjusted without rotating anything.

The current token **expires 2026-12-31**; set a reminder to rotate before
then. Rotation: create a new token on the service account, then
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
