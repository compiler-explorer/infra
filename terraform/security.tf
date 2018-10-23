resource "aws_security_group" "CompilerExplorer" {
  vpc_id = "${aws_vpc.CompilerExplorer.id}"
  name = "gcc-explorer-sg"
  description = "For the GCC explorer"
  tags = {
    Name = "CompilerExplorer"
    Site = "CompilerExplorer"
  }
}

# Compiler explorer nodes do things like `git pull` and `docker pull` at startup,
# so need to be able to talk to the outside world. Ideally they'd be locked down
# completely (with access only to admin node and the ALB); but this would require
# some work to remove the git/docker pull.
resource "aws_security_group_rule" "CE_EgressToAll" {
  security_group_id = "${aws_security_group.CompilerExplorer.id}"
  type = "egress"
  from_port = 0
  to_port = 65535
  cidr_blocks = [
    "0.0.0.0/0"]
  ipv6_cidr_blocks = [
    "::/0"]
  protocol = "-1"
  description = "Unfettered outbound access"
}

resource "aws_security_group_rule" "CE_SshFromAdminNode" {
  security_group_id = "${aws_security_group.CompilerExplorer.id}"
  type = "ingress"
  from_port = 22
  to_port = 22
  source_security_group_id = "${aws_security_group.AdminNode.id}"
  protocol = "tcp"
  description = "Allow SSH access from the admin node only"
}

resource "aws_security_group_rule" "CE_HttpFromAlb" {
  security_group_id = "${aws_security_group.CompilerExplorer.id}"
  type = "ingress"
  from_port = 80
  to_port = 80
  source_security_group_id = "${aws_security_group.CompilerExplorerAlb.id}"
  protocol = "tcp"
  description = "Allow HTTP access from the ALB"
}

resource "aws_security_group_rule" "CE_HttpsFromAlb" {
  security_group_id = "${aws_security_group.CompilerExplorer.id}"
  type = "ingress"
  from_port = 443
  to_port = 443
  source_security_group_id = "${aws_security_group.CompilerExplorerAlb.id}"
  protocol = "tcp"
  description = "Allow HTTPS access from the ALB"
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

# Only needed because compiler-explorer.com uses http...cos the cert on the ALB is for godbolt.org
resource "aws_security_group_rule" "ALB_HttpFromAnywhere" {
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

resource "aws_security_group" "AdminNode" {
  vpc_id = "${aws_vpc.CompilerExplorer.id}"
  name = "AdminNodeSecGroup"
  description = "Security for the admin node"
  tags = {
    Name = "AdminNode"
    Site = "CompilerExplorer"
  }
}

resource "aws_security_group_rule" "Admin_Mosh" {
  security_group_id = "${aws_security_group.AdminNode.id}"
  type = "ingress"
  from_port = 60000
  to_port = 61000
  cidr_blocks = [
    "0.0.0.0/0"]
  ipv6_cidr_blocks = [
    "::/0"]
  protocol = "udp"
  description = "Allow MOSH from anywhere"
}

resource "aws_security_group_rule" "Admin_SSH" {
  security_group_id = "${aws_security_group.AdminNode.id}"
  type = "ingress"
  from_port = 22
  to_port = 22
  cidr_blocks = [
    "0.0.0.0/0"]
  ipv6_cidr_blocks = [
    "::/0"]
  protocol = "tcp"
  description = "Allow SSH from anywhere"
}

resource "aws_security_group_rule" "Admin_EgressToAnywhere" {
  security_group_id = "${aws_security_group.AdminNode.id}"
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
