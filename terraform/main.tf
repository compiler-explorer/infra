provider "aws" {
  region = "us-east-1"
  default_tags {
    tags = {
      Site = "CompilerExplorer"
    }
  }
}

terraform {
  required_version = "~> 1.11.4"
  required_providers {
    aws = {
      source  = "hashicorp/aws",
      version = "~> 6.66" # >= 6.66 keeps key_schema GSI edits in place (see dynamodb.tf)
    }
  }
  backend "s3" {
    bucket = "compiler-explorer"
    key    = "terraform/terraform.tfstate"
    region = "us-east-1"
  }
}
