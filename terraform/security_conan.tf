resource "aws_security_group" "CompilerExplorerConan" {
  vpc_id      = aws_vpc.CompilerExplorer.id
  name        = "gcc-explorer-conan-sg"
  description = "For conan server"
  tags        = {
    Name = "CompilerExplorerConan"
    Site = "CompilerExplorer"
  }
}

resource "aws_security_group_rule" "CEConan_EgressToAll" {
  security_group_id = aws_security_group.CompilerExplorerConan.id
  type              = "egress"
  from_port         = 0
  to_port           = 65535
  cidr_blocks       = ["0.0.0.0/0"]
  ipv6_cidr_blocks  = ["::/0"]
  protocol          = "-1"
  description       = "Unfettered outbound access"
}

resource "aws_security_group_rule" "CEConan_SshFromAdminNode" {
  security_group_id        = aws_security_group.CompilerExplorerConan.id
  type                     = "ingress"
  from_port                = 22
  to_port                  = 22
  source_security_group_id = aws_security_group.AdminNode.id
  protocol                 = "tcp"
  description              = "Allow SSH access from the admin node only"
}

resource "aws_security_group_rule" "CEConan_HttpFromAlb" {
  security_group_id        = aws_security_group.CompilerExplorerConan.id
  type                     = "ingress"
  from_port                = 80
  to_port                  = 80
  source_security_group_id = aws_security_group.CompilerExplorerConanAlb.id
  protocol                 = "tcp"
  description              = "Allow HTTP access from the ALB"
}

resource "aws_security_group_rule" "CEConan_HttpsFromAlb" {
  security_group_id        = aws_security_group.CompilerExplorerConan.id
  type                     = "ingress"
  from_port                = 443
  to_port                  = 443
  source_security_group_id = aws_security_group.CompilerExplorerConanAlb.id
  protocol                 = "tcp"
  description              = "Allow HTTPS access from the ALB"
}

resource "aws_security_group" "CompilerExplorerConanAlb" {
  vpc_id      = aws_vpc.CompilerExplorer.id
  name        = "ce-conan-alb-sg"
  description = "Load balancer security group"
  tags        = {
    Name = "ConanLoadBalancer"
    Site = "CompilerExplorer"
  }
}

resource "aws_security_group_rule" "CeConanALB_HttpsFromAnywhere" {
  security_group_id = aws_security_group.CompilerExplorerConanAlb.id
  type              = "ingress"
  from_port         = 443
  to_port           = 443
  cidr_blocks       = ["0.0.0.0/0"]
  ipv6_cidr_blocks  = ["::/0"]
  protocol          = "tcp"
  description       = "Allow HTTPS access from anywhere"
}

resource "aws_security_group_rule" "CeConanALB_EgressToAnywhere" {
  security_group_id = aws_security_group.CompilerExplorerConanAlb.id
  type              = "egress"
  from_port         = 0
  to_port           = 65535
  cidr_blocks       = ["0.0.0.0/0"]
  ipv6_cidr_blocks  = ["::/0"]
  protocol          = "-1"
  description       = "Allow egress to anywhere"
}

resource "aws_security_group_rule" "CeConanALB_IngressFromCE" {
  security_group_id        = aws_security_group.CompilerExplorerConanAlb.id
  type                     = "ingress"
  from_port                = 0
  to_port                  = 65535
  source_security_group_id = aws_security_group.CompilerExplorerConan.id
  protocol                 = "tcp"
  description              = "Allow ingress from CE nodes"
}
