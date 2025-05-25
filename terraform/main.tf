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
      version = "~> 5.96.0"
    }
  }
  backend "s3" {
    bucket = "compiler-explorer"
    key    = "terraform/terraform.tfstate"
    region = "us-east-1"
  }
}
