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
  prom_datasource_uid = "grafanacloud-prom"
  # Existing, hand-made contact point. Referenced by name until it is imported
  # and managed here.
  contact_point_admins = "Discord Admins"
}
