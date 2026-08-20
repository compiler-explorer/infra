# Grafana Cloud configuration in Terraform

`terraform/grafana/` manages part of our Grafana Cloud stack
(`https://ce.grafana.net`): the alert rules we rely on, and over time the
contact points and key dashboards. Terraform only touches resources declared
there; ad-hoc dashboards and experiments made in the UI are invisible to it.

Managed today: folder **CE Alerts** and its rule groups -- Instance Restarts
(app restarted in place, infra#2313), Host Disk (root and conan-server disks
low, infra#2310), Staging Instances (staging left running). Every hand-made
alert has been adopted or replaced; the remaining rules in the stack
(`integrations-linux-node`, synthetic monitoring) are vendor/plugin-owned --
leave them alone. Contact points are still hand-made; rules reference
"Discord Admins" by name.

Provisioned rules are read-only in the UI (the "Provisioned" badge); use
silences during incidents. To experiment, build a rule in another folder,
then port it to HCL -- `GET /api/v1/provisioning/alert-rules/export?format=hcl`
gives a starting point.

## Running

A normal Terraform root with its own state
(`s3://compiler-explorer/terraform/grafana.tfstate`). `terraform init/plan/apply`
in `terraform/grafana`, or `make grafana-init/-plan/-apply`. The AWS root is
separate and never needs Grafana credentials.

## Credentials

The provider reads a token for the `terraform-infra` service account (basic
role Editor) from SSM `/admin/grafanaTerraformToken`, so anyone with AWS
credentials can plan and apply. The token lands in the grafana state file,
same exposure as other secrets in the AWS state. Current token expires
**2026-12-31**; rotate by creating a new service-account token and
`aws ssm put-parameter --overwrite`.

Folders with restricted permissions are invisible to the service account;
rules in them cannot be listed, adopted or deleted with this token.

## Adopting existing objects

Add an `import {}` block plus the matching resource in one PR; delete the
block once applied. (The legacy `terraform import` command does not work here
because the provider config depends on a data source.) Import ids:

- `grafana_folder`: folder uid (from the `/dashboards/f/<uid>/` URL)
- `grafana_rule_group`: `"<folder uid>:<group name>"`; keep existing rule uids
  for in-place updates
- `grafana_contact_point`: the name. Secure fields export as `[REDACTED]`, so
  supply the real value (via `data "aws_ssm_parameter"`); it then sits in state
- `grafana_dashboard`: dashboard uid; keep JSON in a file via `config_json`

Deliberately not managed: the notification policy tree (a singleton; rules use
`notification_settings` to name a contact point directly, bypassing it) and
the node-side agent config (`grafana/agent.yaml`, baked into images).

## Adding a rule

Copy an existing `rule {}`: instant Prometheus query `A` on
`grafanacloud-prom`, threshold expression `B`, `condition = "B"`,
`notification_settings` naming the contact point, and a stable `uid`. If a
perpetual `model` diff appears after apply, paste the normalised `model` from
the export endpoint above.
