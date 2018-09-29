resource "aws_security_group" "CompilerExplorer" {
  vpc_id = "${aws_vpc.CompilerExplorer.id}"
  name = "gcc-explorer-sg"
  description = "For the GCC explorer"
  tags = {
    Name = "CompilerExplorer"
    Site = "CompilerExplorer"
  }
}

resource "aws_security_group_rule" "CE_EgressToAnywhere" {
  security_group_id = "${aws_security_group.CompilerExplorer.id}"
  type = "egress"
  from_port = 0
  to_port = 65535
  cidr_blocks = [
    "0.0.0.0/0"]
  ipv6_cidr_blocks = [
    "::/0"]
  protocol = "-1"
  description = "Allow egress to anywhere"
}

resource "aws_security_group_rule" "CE_SshFromAnywhere" {
  security_group_id = "${aws_security_group.CompilerExplorer.id}"
  type = "ingress"
  from_port = 22
  to_port = 22
  cidr_blocks = [
    "0.0.0.0/0"]
  ipv6_cidr_blocks = [
    "::/0"]
  protocol = "tcp"
  description = "Allow SSH access from anywhere"
}

resource "aws_security_group_rule" "CE_WebFromAnywhere" {
  security_group_id = "${aws_security_group.CompilerExplorer.id}"
  type = "ingress"
  from_port = 80
  to_port = 80
  cidr_blocks = [
    "0.0.0.0/0"]
  ipv6_cidr_blocks = [
    "::/0"]
  protocol = "tcp"
  description = "Allow WWW access from anywhere"
}

resource "aws_security_group_rule" "CE_HttpsFromAnywhere" {
  security_group_id = "${aws_security_group.CompilerExplorer.id}"
  type = "ingress"
  from_port = 443
  to_port = 443
  cidr_blocks = [
    "0.0.0.0/0"]
  ipv6_cidr_blocks = [
    "::/0"]
  protocol = "tcp"
  description = "Allow WWW access from anywhere"
}

resource "aws_security_group" "CompilerExplorerAlb" {
  vpc_id = "${aws_vpc.CompilerExplorer.id}"
  name = "ce-alb-sg"
  description = "Load balancer security group"
  tags = {
    Name = "CELoadBalancer"
    Site = "CompilerExplorer"
  }
}
/*
resource "aws_security_group_rule" "ALB_WebFromAnywhere" {
  security_group_id = "${aws_security_group.CompilerExplorerAlb.id}"
  type = "ingress"
  from_port = 80
  to_port = 80
  cidr_blocks = [
    "0.0.0.0/0"]
  ipv6_cidr_blocks = [
    "::/0"]
  protocol = "tcp"
  description = "Allow HTTP access from anywhere"
}*/

resource "aws_security_group_rule" "ALB_HttpsFromAnywhere" {
  security_group_id = "${aws_security_group.CompilerExplorerAlb.id}"
  type = "ingress"
  from_port = 443
  to_port = 443
  cidr_blocks = [
    "0.0.0.0/0"]
  ipv6_cidr_blocks = [
    "::/0"]
  protocol = "tcp"
  description = "Allow HTTPS access from anywhere"
}

resource "aws_security_group_rule" "ALB_EgressToAnywhere" {
  security_group_id = "${aws_security_group.CompilerExplorerAlb.id}"
  type = "egress"
  from_port = 0
  to_port = 65535
  cidr_blocks = [
    "0.0.0.0/0"]
  ipv6_cidr_blocks = [
    "::/0"]
  protocol = "-1"
  description = "Allow egress to anywhere"
}
