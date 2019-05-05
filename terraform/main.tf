provider "aws" {
  region  = "us-east-1"
  version = "~> 1.42"
}

terraform {
  required_version = "~> 0.11"
  backend "s3" {
    bucket = "compiler-explorer"
    key    = "terraform/terraform.tfstate"
    region = "us-east-1"
  }
}
