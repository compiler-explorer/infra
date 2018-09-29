# Config from environment
provider "aws" {
  region = "us-east-1"
}

terraform {
  backend "s3" {
    bucket = "compiler-explorer"
    key = "terraform/terraform.tfstate"
    region = "us-east-1"
  }
}