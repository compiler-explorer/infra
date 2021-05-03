provider "aws" {
  region  = "us-east-1"
  default_tags {
    tags = {
      Site = "CompilerExplorer"
    }
  }
}

terraform {
  required_version = "~> 0.13"
  required_providers {
    aws = {
      source = "hashicorp/aws",
      version = "~> 3.38.0"
    }
  }
  backend "s3" {
    bucket = "compiler-explorer"
    key    = "terraform/terraform.tfstate"
    region = "us-east-1"
  }
}
