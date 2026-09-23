# Grafana Cloud configuration managed as code. Deliberately a separate root
# from ../ (the AWS root) so an AWS apply never needs Grafana credentials and a
# Grafana hiccup never blocks an AWS change. Only what is declared here is
# managed; ad-hoc dashboards, folders and rules made in the UI are untouched.
# See docs/grafana_terraform.md.

terraform {
  required_version = "~> 1.11.4"
  required_providers {
    grafana = {
      source  = "grafana/grafana"
      version = "~> 4.45"
    }
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.24"
    }
  }
  backend "s3" {
    bucket       = "compiler-explorer"
    key          = "terraform/grafana.tfstate"
    region       = "us-east-1"
    use_lockfile = true
  }
}

provider "aws" {
  region = "us-east-1"
}

# Token for the "terraform-infra" service account on the ce.grafana.net stack,
# read from SSM so anyone with AWS credentials can plan/apply with plain
# terraform and nothing secret lives on disk. Kept under /admin/ (not
# /compiler-explorer/, which every CE node can read). Rotate by creating a new
# service account token and `aws ssm put-parameter --overwrite`.
data "aws_ssm_parameter" "grafana_token" {
  name            = "/admin/grafanaTerraformToken"
  with_decryption = true
}

provider "grafana" {
  url  = "https://ce.grafana.net"
  auth = data.aws_ssm_parameter.grafana_token.value
}

locals {
  prom_datasource_uid  = "grafanacloud-prom"
  contact_point_admins = grafana_contact_point.admins.name
}

# Same webhook the AWS root's cloudwatch_to_discord Lambda posts to, so every alert lands in one channel.
data "aws_ssm_parameter" "discord_webhook_url" {
  name            = "/admin/discord_webhook_url"
  with_decryption = true
}

# The whole policy tree; the root route catches alerts that name no contact point (e.g. synthetic monitoring).
resource "grafana_notification_policy" "root" {
  contact_point      = grafana_contact_point.admins.name
  group_by           = ["grafana_folder", "alertname"]
  disable_provenance = true

  policy {
    contact_point = grafana_contact_point.admins.name
    continue      = true
    matcher {
      label = "__contacts__"
      match = "=~"
      value = ".*\"Discord Admins\".*"
    }
  }
  policy {
    contact_point = "Discord Admins Microsoft"
    continue      = true
    matcher {
      label = "__contacts__"
      match = "=~"
      value = ".*\"Discord Admins Microsoft\".*"
    }
  }
  policy {
    contact_point = "Mail MS"
    continue      = true
    matcher {
      label = "__contacts__"
      match = "=~"
      value = ".*\"Mail MS\".*"
    }
  }
}

resource "grafana_contact_point" "admins" {
  name = "Discord Alerts"
  discord {
    url = data.aws_ssm_parameter.discord_webhook_url.value
  }
  lifecycle {
    create_before_destroy = true
  }
}
