provider "aws" {
  region  = "us-east-1"
  version = "~> 3.7"
}

terraform {
  required_version = "~> 0.13"
  backend "s3" {
    bucket = "compiler-explorer"
    key    = "terraform/terraform.tfstate"
    region = "us-east-1"
  }
}
