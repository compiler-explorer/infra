resource "aws_security_group" "CompilerExplorer" {
  vpc_id      = aws_vpc.CompilerExplorer.id
  name        = "gcc-explorer-sg"
  description = "For the GCC explorer"
  tags        = {
    Name = "CompilerExplorer"
  }
}

# It's convenient for Compiler explorer nodes to be able to do things like `git pull` and `docker pull`,
# so need to be able to talk to the outside world. Ideally they'd be locked down
# completely (with access only to admin node and the ALB); but this would make diagnosing and fixing
# issues quickly on-box very difficult.
resource "aws_security_group_rule" "CE_EgressToAll" {
  security_group_id = aws_security_group.CompilerExplorer.id
  type              = "egress"
  from_port         = 0
  to_port           = 65535
  cidr_blocks       = ["0.0.0.0/0"]
  ipv6_cidr_blocks  = ["::/0"]
  protocol          = "-1"
  description       = "Unfettered outbound access"
}

resource "aws_security_group_rule" "CE_SshFromAdminNode" {
  security_group_id        = aws_security_group.CompilerExplorer.id
  type                     = "ingress"
  from_port                = 22
  to_port                  = 22
  source_security_group_id = aws_security_group.AdminNode.id
  protocol                 = "tcp"
  description              = "Allow SSH access from the admin node only"
}

resource "aws_security_group_rule" "CE_HttpFromAlb" {
  security_group_id        = aws_security_group.CompilerExplorer.id
  type                     = "ingress"
  from_port                = 80
  to_port                  = 80
  source_security_group_id = aws_security_group.CompilerExplorerAlb.id
  protocol                 = "tcp"
  description              = "Allow HTTP access from the ALB"
}

resource "aws_security_group_rule" "CE_ConanHttpFromAlb" {
  security_group_id        = aws_security_group.CompilerExplorer.id
  type                     = "ingress"
  from_port                = 1080
  to_port                  = 1080
  source_security_group_id = aws_security_group.CompilerExplorerAlb.id
  protocol                 = "tcp"
  description              = "Allow HTTP access from the ALB"
}

resource "aws_security_group_rule" "CE_HttpsFromAlb" {
  security_group_id        = aws_security_group.CompilerExplorer.id
  type                     = "ingress"
  from_port                = 443
  to_port                  = 443
  source_security_group_id = aws_security_group.CompilerExplorerAlb.id
  protocol                 = "tcp"
  description              = "Allow HTTPS access from the ALB"
}

resource "aws_security_group_rule" "CE_ConanHttpsFromAlb" {
  security_group_id        = aws_security_group.CompilerExplorer.id
  type                     = "ingress"
  from_port                = 1443
  to_port                  = 1443
  source_security_group_id = aws_security_group.CompilerExplorerAlb.id
  protocol                 = "tcp"
  description              = "Allow HTTPS access from the ALB"
}

resource "aws_security_group" "CompilerExplorerAlb" {
  vpc_id      = aws_vpc.CompilerExplorer.id
  name        = "ce-alb-sg"
  description = "Load balancer security group"
  tags        = {
    Name = "CELoadBalancer"
  }
}

resource "aws_security_group_rule" "ALB_HttpsFromAnywhere" {
  security_group_id = aws_security_group.CompilerExplorerAlb.id
  type              = "ingress"
  from_port         = 443
  to_port           = 443
  cidr_blocks       = ["0.0.0.0/0"]
  ipv6_cidr_blocks  = ["::/0"]
  protocol          = "tcp"
  description       = "Allow HTTPS access from anywhere"
}

resource "aws_security_group_rule" "ALB_ConanHttpsFromAnywhere" {
  security_group_id = aws_security_group.CompilerExplorerAlb.id
  type              = "ingress"
  from_port         = 1443
  to_port           = 1443
  cidr_blocks       = ["0.0.0.0/0"]
  ipv6_cidr_blocks  = ["::/0"]
  protocol          = "tcp"
  description       = "Allow HTTPS access from anywhere"
}

resource "aws_security_group_rule" "ALB_EgressToAnywhere" {
  security_group_id = aws_security_group.CompilerExplorerAlb.id
  type              = "egress"
  from_port         = 0
  to_port           = 65535
  cidr_blocks       = ["0.0.0.0/0"]
  ipv6_cidr_blocks  = ["::/0"]
  protocol          = "-1"
  description       = "Allow egress to anywhere"
}

resource "aws_security_group_rule" "ALB_IngressFromCE" {
  security_group_id        = aws_security_group.CompilerExplorerAlb.id
  type                     = "ingress"
  from_port                = 0
  to_port                  = 65535
  source_security_group_id = aws_security_group.CompilerExplorer.id
  protocol                 = "tcp"
  description              = "Allow ingress from CE nodes"
}

resource "aws_security_group" "AdminNode" {
  vpc_id      = aws_vpc.CompilerExplorer.id
  name        = "AdminNodeSecGroup"
  description = "Security for the admin node"
  tags        = {
    Name = "AdminNode"
  }
}

resource "aws_security_group_rule" "Admin_Mosh" {
  security_group_id = aws_security_group.AdminNode.id
  type              = "ingress"
  from_port         = 60000
  to_port           = 61000
  cidr_blocks       = ["0.0.0.0/0"]
  ipv6_cidr_blocks  = ["::/0"]
  protocol          = "udp"
  description       = "Allow MOSH from anywhere"
}

resource "aws_security_group_rule" "Admin_SSH" {
  security_group_id = aws_security_group.AdminNode.id
  type              = "ingress"
  from_port         = 22
  to_port           = 22
  cidr_blocks       = ["0.0.0.0/0"]
  ipv6_cidr_blocks  = ["::/0"]
  protocol          = "tcp"
  description       = "Allow SSH from anywhere"
}

resource "aws_security_group_rule" "Admin_winRM" {
  # this is here as we (lazily) use the admin sec group for the packer builds.
  security_group_id = aws_security_group.AdminNode.id
  type              = "ingress"
  from_port         = 5986
  to_port           = 5986
  cidr_blocks       = ["0.0.0.0/0"]
  ipv6_cidr_blocks  = ["::/0"]
  protocol          = "tcp"
  description       = "Allow secure winrm from anywhere"
}

resource "aws_security_group_rule" "Admin_EgressToAnywhere" {
  security_group_id = aws_security_group.AdminNode.id
  type              = "egress"
  from_port         = 0
  to_port           = 65535
  cidr_blocks       = ["0.0.0.0/0"]
  ipv6_cidr_blocks  = ["::/0"]
  protocol          = "-1"
  description       = "Allow egress to anywhere"
}

resource "aws_security_group_rule" "Admin_IngressFromCE" {
  security_group_id        = aws_security_group.AdminNode.id
  type                     = "egress"
  from_port                = 0
  to_port                  = 65535
  source_security_group_id = aws_security_group.CompilerExplorer.id
  protocol                 = "tcp"
  description              = "Allow ingress from CE nodes"
}

data "aws_iam_policy_document" "InstanceAssumeRolePolicy" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      identifiers = ["ec2.amazonaws.com"]
      type        = "Service"
    }
  }
}

resource "aws_iam_role" "CompilerExplorerRole" {
  name               = "CompilerExplorerRole"
  description        = "Compiler Explorer node role"
  assume_role_policy = data.aws_iam_policy_document.InstanceAssumeRolePolicy.json
}

data "aws_iam_policy" "CloudWatchAgentServerPolicy" {
  arn = "arn:aws:iam::052730242331:policy/CloudWatchAgentServerPolicy"
}

data "aws_iam_policy_document" "CeModifyStoredState" {
  statement {
    sid       = "DatabaseAccessSid"
    actions   = [
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
      "dynamodb:DescribeTable",
      "dynamodb:GetItem",
      "dynamodb:Scan",
      "dynamodb:Query"
    ]
    resources = [aws_dynamodb_table.links.arn]
  }
  statement {
    sid       = "S3AccessSid"
    actions   = ["s3:*"]
    resources = [
      "${aws_s3_bucket.storage-godbolt-org.arn}/*",
      aws_s3_bucket.storage-godbolt-org.arn
    ]
  }
}

resource "aws_iam_policy" "CeModifyStoredState" {
  name        = "CeModifyStoredState"
  description = "Can create and list short links for compiler explorer"
  policy      = data.aws_iam_policy_document.CeModifyStoredState.json
}

data "aws_iam_policy_document" "AccessCeParams" {
  statement {
    actions   = [
      "ssm:Describe*",
      "ssm:Get*",
      "ssm:List*"
    ]
    // TODO is there a way to refer to this (external) parameter (CC @Cosaquee)
    resources = ["arn:aws:ssm:us-east-1:052730242331:parameter/compiler-explorer/*"]
  }
}

resource "aws_iam_policy" "AccessCeParams" {
  name        = "AccessCeParams"
  description = "Can read Compiler Explorer parameters/secrets"
  policy      = data.aws_iam_policy_document.AccessCeParams.json
}

data "aws_iam_policy_document" "ReadS3Minimal" {
  statement {
    actions   = ["s3:Get*"]
    resources = [
      "${aws_s3_bucket.compiler-explorer.arn}/authorized_keys/*",
      "${aws_s3_bucket.compiler-explorer.arn}/version/*"
    ]
  }
}

resource "aws_iam_policy" "ReadS3Minimal" {
  name        = "ReadS3Minimal"
  description = "Minimum possible read acces to S3 to boot an instance"
  policy      = data.aws_iam_policy_document.ReadS3Minimal.json
}

resource "aws_iam_instance_profile" "CompilerExplorerRole" {
  name = "CompilerExplorerRole"
  role = aws_iam_role.CompilerExplorerRole.name
}

resource "aws_iam_role_policy_attachment" "CompilerExplorerRole_attach_CloudWatchAgentServerPolicy" {
  role       = aws_iam_role.CompilerExplorerRole.name
  policy_arn = data.aws_iam_policy.CloudWatchAgentServerPolicy.arn
}

resource "aws_iam_role_policy_attachment" "CompilerExplorerRole_attach_CeModifyStoredState" {
  role       = aws_iam_role.CompilerExplorerRole.name
  policy_arn = aws_iam_policy.CeModifyStoredState.arn
}

resource "aws_iam_role_policy_attachment" "CompilerExplorerRole_attach_AccessCeParams" {
  role       = aws_iam_role.CompilerExplorerRole.name
  policy_arn = aws_iam_policy.AccessCeParams.arn
}

resource "aws_iam_role_policy_attachment" "CompilerExplorerRole_attach_ReadS3Minimal" {
  role       = aws_iam_role.CompilerExplorerRole.name
  policy_arn = aws_iam_policy.ReadS3Minimal.arn
}

// This is for the auth node temporarily to allow port 3000 from the alb
resource "aws_security_group_rule" "CE_AuthHttpFromAlb" {
  security_group_id        = aws_security_group.AdminNode.id
  type                     = "ingress"
  from_port                = 3000
  to_port                  = 3000
  source_security_group_id = aws_security_group.CompilerExplorerAlb.id
  protocol                 = "tcp"
  description              = "Allow port 3000 access from the ALB"
}
