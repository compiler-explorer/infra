resource "aws_vpc" "CompilerExplorer" {
  cidr_block = "172.30.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support = true
  instance_tenancy = "default"

  tags {
    Name = "CompilerExplorer"
    Site = "CompilerExplorer"
  }
}

resource "aws_subnet" "ce-1a" {
  vpc_id = "${aws_vpc.CompilerExplorer.id}"
  cidr_block = "172.30.0.0/24"
  availability_zone = "us-east-1a"
  map_public_ip_on_launch = true

  tags {
    Name = "CompilerExplorer1a"
    Site = "CompilerExplorer"
  }
}

resource "aws_subnet" "ce-1b" {
  vpc_id = "${aws_vpc.CompilerExplorer.id}"
  cidr_block = "172.30.1.0/24"
  availability_zone = "us-east-1b"
  map_public_ip_on_launch = true

  tags {
    Name = "CompilerExplorer1b"
    Site = "CompilerExplorer"
  }
}

resource "aws_subnet" "ce-1c" {
  vpc_id = "${aws_vpc.CompilerExplorer.id}"
  cidr_block = "172.30.4.0/24"
  availability_zone = "us-east-1c"
  map_public_ip_on_launch = true

  tags {
    Name = "CompilerExplorer1c"
    Site = "CompilerExplorer"
  }
}

resource "aws_subnet" "ce-1d" {
  vpc_id = "${aws_vpc.CompilerExplorer.id}"
  cidr_block = "172.30.2.0/24"
  availability_zone = "us-east-1d"
  map_public_ip_on_launch = true

  tags {
    Name = "CompilerExplorer1d"
    Site = "CompilerExplorer"
  }
}

resource "aws_subnet" "ce-1e" {
  vpc_id = "${aws_vpc.CompilerExplorer.id}"
  cidr_block = "172.30.6.0/24"
  availability_zone = "us-east-1e"
  map_public_ip_on_launch = true

  tags {
    Name = "CompilerExplorer1e"
    Site = "CompilerExplorer"
  }
}

resource "aws_subnet" "ce-1f" {
  vpc_id = "${aws_vpc.CompilerExplorer.id}"
  cidr_block = "172.30.5.0/24"
  availability_zone = "us-east-1f"
  map_public_ip_on_launch = true

  tags {
    Name = "CompilerExplorer1f"
    Site = "CompilerExplorer"
  }
}
