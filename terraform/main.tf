provider "aws" {
  region  = "us-east-1"
  version = "~> 2.66"
}

terraform {
  required_version = "~> 0.12"
  backend "s3" {
    bucket = "compiler-explorer"
    key    = "terraform/terraform.tfstate"
    region = "us-east-1"
  }
}
