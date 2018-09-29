resource "aws_vpc" "CompilerExplorer" {
  cidr_block = "172.30.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support = true
  instance_tenancy = "default"

  tags {
    "Name" = "CompilerExplorer"
    "Site" = "CompilerExplorer"
  }
}

