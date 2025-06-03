resource "aws_security_group" "CompilerExplorer" {
  vpc_id      = module.ce_network.vpc.id
  name        = "gcc-explorer-sg"
  description = "For the GCC explorer"
  tags = {
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

resource "aws_security_group_rule" "CE_SmbLocally" {
  security_group_id        = aws_security_group.CompilerExplorer.id
  type                     = "ingress"
  from_port                = 445
  to_port                  = 445
  source_security_group_id = aws_security_group.CompilerExplorer.id
  protocol                 = "tcp"
  description              = "Allow SMB access locally"
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

resource "aws_security_group_rule" "CE_HttpFromAdminNode" {
  security_group_id        = aws_security_group.CompilerExplorer.id
  type                     = "ingress"
  from_port                = 80
  to_port                  = 80
  source_security_group_id = aws_security_group.AdminNode.id
  protocol                 = "tcp"
  description              = "Allow HTTP access from admin node for health checks"
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
  vpc_id      = module.ce_network.vpc.id
  name        = "ce-alb-sg"
  description = "Load balancer security group"
  tags = {
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
  vpc_id      = module.ce_network.vpc.id
  name        = "AdminNodeSecGroup"
  description = "Security for the admin node"
  tags = {
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

resource "aws_iam_role" "CompilerExplorerWindowsRole" {
  name               = "CompilerExplorerWindowsRole"
  description        = "Compiler Explorer Windows node role"
  assume_role_policy = data.aws_iam_policy_document.InstanceAssumeRolePolicy.json
}

data "aws_iam_policy" "CloudWatchAgentServerPolicy" {
  arn = "arn:aws:iam::052730242331:policy/CloudWatchAgentServerPolicy"
}

data "aws_iam_policy_document" "CeModifyStoredState" {
  statement {
    sid = "DatabaseAccessSid"
    actions = [
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
    sid     = "S3AccessSid"
    actions = ["s3:*"]
    resources = [
      "${aws_s3_bucket.storage-godbolt-org.arn}/*",
      aws_s3_bucket.storage-godbolt-org.arn
    ]
  }
}

resource "aws_iam_policy" "ScanLibraryBuildHistory" {
  name        = "ScanLibraryBuildHistory"
  description = "Can scan/query library build history"
  policy      = data.aws_iam_policy_document.ScanLibraryBuildHistory.json
}

data "aws_iam_policy_document" "ScanLibraryBuildHistory" {
  statement {
    sid = "ScanLibraryBuildHistory"
    actions = [
      "dynamodb:Scan",
      "dynamodb:Query"
    ]
    resources = [aws_dynamodb_table.library-build-history.arn]
  }
}

resource "aws_iam_policy" "UpdateLibraryBuildHistory" {
  name        = "UpdateLibraryBuildHistory"
  description = "Can update library build history"
  policy      = data.aws_iam_policy_document.UpdateLibraryBuildHistory.json
}

data "aws_iam_policy_document" "UpdateLibraryBuildHistory" {
  statement {
    sid = "UpdateLibraryBuildHistory"
    actions = [
      "dynamodb:PutItem",
      "dynamodb:UpdateItem"
    ]
    resources = [aws_dynamodb_table.library-build-history.arn]
  }
}

resource "aws_iam_policy" "CeModifyStoredState" {
  name        = "CeModifyStoredState"
  description = "Can create and list short links for compiler explorer"
  policy      = data.aws_iam_policy_document.CeModifyStoredState.json
}

data "aws_iam_policy_document" "ReadGooGlLinks" {
  statement {
    sid = "ReadGooGlLinks"
    actions = [
      "dynamodb:GetItem"
    ]
    resources = [aws_dynamodb_table.goo_gl_links.arn]
  }
}

resource "aws_iam_policy" "ReadGooGlLinks" {
  name        = "ReadGooGlLinks"
  description = "Read-only access to goo.gl links table"
  policy      = data.aws_iam_policy_document.ReadGooGlLinks.json
}

data "aws_iam_policy_document" "CePutCompileStatsLog" {
  statement {
    sid     = "CePutCompileStatsLog"
    actions = ["s3:PutObject"]
    resources = [
      "${aws_s3_bucket.compiler-explorer-logs.arn}/compile-stats/*"
    ]
  }
}

resource "aws_iam_policy" "CePutCompileStatsLog" {
  name        = "CePutCompileStatsLog"
  description = "Can write to compile-stats log bucket"
  policy      = data.aws_iam_policy_document.CePutCompileStatsLog.json
}

data "aws_iam_policy_document" "CeSqsPushPop" {
  statement {
    sid = "CeSqsPushPop"
    actions = [
      "sqs:SendMessage",
      "sqs:ReceiveMessage",
      "sqs:DeleteMessage"
    ]
    resources = [
      aws_sqs_queue.prod-execqueue-aarch64-linux-cpu.arn,
      aws_sqs_queue.staging-execqueue-aarch64-linux-cpu.arn,
    ]
  }
}

resource "aws_iam_policy" "CeSqsPushPop" {
  name        = "CeSqsPushPop"
  description = "Can push/pop Sqs"
  policy      = data.aws_iam_policy_document.CeSqsPushPop.json
}

data "aws_iam_policy_document" "AccessCeParams" {
  statement {
    actions = [
      "ssm:Describe*",
      "ssm:Get*",
      "ssm:List*"
    ]
    // These secrets are externally managed. There's no way I can find to refer to them using data stanzas without
    // storing their contents here too.
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
    actions = ["s3:Get*"]
    resources = [
      "${aws_s3_bucket.compiler-explorer.arn}/authorized_keys/*",
      "${aws_s3_bucket.compiler-explorer.arn}/version/*"
    ]
  }
}

resource "aws_iam_policy" "ReadS3Minimal" {
  name        = "ReadS3Minimal"
  description = "Minimum possible read access to S3 to boot an instance"
  policy      = data.aws_iam_policy_document.ReadS3Minimal.json
}

resource "aws_iam_instance_profile" "CompilerExplorerRole" {
  name = "CompilerExplorerRole"
  role = aws_iam_role.CompilerExplorerRole.name
}

resource "aws_iam_instance_profile" "CompilerExplorerWindowsRole" {
  name = "CompilerExplorerWindowsRole"
  role = aws_iam_role.CompilerExplorerWindowsRole.name
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

resource "aws_iam_role_policy_attachment" "CompilerExplorerRole_attach_WriteCompileStatsLogs" {
  role       = aws_iam_role.CompilerExplorerRole.name
  policy_arn = aws_iam_policy.CePutCompileStatsLog.arn
}

resource "aws_iam_role_policy_attachment" "CompilerExplorerRole_attach_CeSqsPushPop" {
  role       = aws_iam_role.CompilerExplorerRole.name
  policy_arn = aws_iam_policy.CeSqsPushPop.arn
}

resource "aws_iam_role_policy_attachment" "CompilerExplorerRole_attach_ScanLibraryBuildHistory" {
  role       = aws_iam_role.CompilerExplorerRole.name
  policy_arn = aws_iam_policy.ScanLibraryBuildHistory.arn
}

resource "aws_iam_role_policy_attachment" "CompilerExplorerRole_attach_ReadGooGlLinks" {
  role       = aws_iam_role.CompilerExplorerRole.name
  policy_arn = aws_iam_policy.ReadGooGlLinks.arn
}

// CompilerExplorerRole but for Windows machines
resource "aws_iam_role_policy_attachment" "CompilerExplorerWindowsRole_attach_CloudWatchAgentServerPolicy" {
  role       = aws_iam_role.CompilerExplorerWindowsRole.name
  policy_arn = data.aws_iam_policy.CloudWatchAgentServerPolicy.arn
}

resource "aws_iam_role_policy_attachment" "CompilerExplorerWindowsRole_attach_CeModifyStoredState" {
  role       = aws_iam_role.CompilerExplorerWindowsRole.name
  policy_arn = aws_iam_policy.CeModifyStoredState.arn
}

resource "aws_iam_role_policy_attachment" "CompilerExplorerWindowsRole_attach_WriteCompileStatsLogs" {
  role       = aws_iam_role.CompilerExplorerWindowsRole.name
  policy_arn = aws_iam_policy.CePutCompileStatsLog.arn
}

resource "aws_iam_role_policy_attachment" "CompilerExplorerWindowsRole_attach_AccessCeParams" {
  role       = aws_iam_role.CompilerExplorerWindowsRole.name
  policy_arn = aws_iam_policy.AccessCeParams.arn
}

resource "aws_iam_role_policy_attachment" "CompilerExplorerWindowsRole_attach_ReadS3Minimal" {
  role       = aws_iam_role.CompilerExplorerWindowsRole.name
  policy_arn = aws_iam_policy.ReadS3Minimal.arn
}

resource "aws_iam_role_policy_attachment" "CompilerExplorerWindowsRole_attach_AmazonSSMManagedInstanceCore" {
  role       = aws_iam_role.CompilerExplorerWindowsRole.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_role_policy_attachment" "CompilerExplorerWindowsRole_attach_ReadGooGlLinks" {
  role       = aws_iam_role.CompilerExplorerWindowsRole.name
  policy_arn = aws_iam_policy.ReadGooGlLinks.arn
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

resource "aws_security_group" "Builder" {
  vpc_id      = module.ce_network.vpc.id
  name        = "BuilderNodeSecGroup"
  description = "Compiler Explorer compiler and library security group"
  tags = {
    Name = "Builder"
  }
}

// The builder needs to be able to fetch things from the wider internet.
resource "aws_security_group_rule" "Builder_EgressToAll" {
  security_group_id = aws_security_group.Builder.id
  type              = "egress"
  from_port         = 0
  to_port           = 65535
  cidr_blocks       = ["0.0.0.0/0"]
  ipv6_cidr_blocks  = ["::/0"]
  protocol          = "-1"
  description       = "Unfettered outbound access"
}

resource "aws_security_group_rule" "Builder_SshFromAdminNode" {
  security_group_id        = aws_security_group.Builder.id
  type                     = "ingress"
  from_port                = 22
  to_port                  = 22
  source_security_group_id = aws_security_group.AdminNode.id
  protocol                 = "tcp"
  description              = "Allow SSH access from the admin node only"
}

// TODO: remove this comment once we're happy with the builder:
// * builder used to have AmazonSFullAccess and AmazonSSMReadOnlyAccess
resource "aws_iam_role" "Builder" {
  name               = "Builder"
  description        = "Compiler Explorer compiler and library building role"
  assume_role_policy = data.aws_iam_policy_document.InstanceAssumeRolePolicy.json
}

resource "aws_iam_instance_profile" "Builder" {
  name = "Builder"
  role = aws_iam_role.Builder.name
}

resource "aws_iam_role_policy_attachment" "Builder_attach_CloudWatchAgentServerPolicy" {
  role       = aws_iam_role.Builder.name
  policy_arn = data.aws_iam_policy.CloudWatchAgentServerPolicy.arn
}

resource "aws_iam_role_policy_attachment" "Builder_attach_UpdateLibraryBuildHistory" {
  role       = aws_iam_role.Builder.name
  policy_arn = aws_iam_policy.UpdateLibraryBuildHistory.arn
}

data "aws_iam_policy_document" "CeBuilderStorageAccess" {
  statement {
    sid     = "S3Access"
    actions = ["s3:*"]
    resources = [
      "${aws_s3_bucket.compiler-explorer.arn}/opt/*",
      "${aws_s3_bucket.compiler-explorer.arn}/opt-nonfree/*",
      "${aws_s3_bucket.compiler-explorer.arn}/dist/*",
      "${aws_s3_bucket.ce-cdn-net.arn}/*",
    ]
  }
  statement {
    sid = "BuildTableAccess"
    actions = [
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
      "dynamodb:DescribeTable",
      "dynamodb:GetItem",
      "dynamodb:Scan",
      "dynamodb:Query"
    ]
    resources = [aws_dynamodb_table.compiler-builds.arn]
  }
}

resource "aws_iam_policy" "CeBuilderStorageAccess" {
  name        = "CeBuilderStorageAccess"
  description = "Can write to S3 (in the appropriate locations only) and build table "
  policy      = data.aws_iam_policy_document.CeBuilderStorageAccess.json
}

resource "aws_iam_role_policy_attachment" "Builder_attach_CeBuilderStorageAccess" {
  role       = aws_iam_role.Builder.name
  policy_arn = aws_iam_policy.CeBuilderStorageAccess.arn
}

resource "aws_iam_role_policy_attachment" "Builder_attach_AccessCeParams" {
  role       = aws_iam_role.Builder.name
  policy_arn = aws_iam_policy.AccessCeParams.arn
}

resource "aws_iam_role_policy_attachment" "Builder_attach_ReadS3Minimal" {
  role       = aws_iam_role.Builder.name
  policy_arn = aws_iam_policy.ReadS3Minimal.arn
}


resource "aws_security_group" "efs" {
  vpc_id      = module.ce_network.vpc.id
  name        = "EFS"
  description = "EFS access for Compiler Explorer"
  tags = {
    Name = "EFS"
  }
}

resource "aws_security_group_rule" "efs_outbound" {
  lifecycle {
    create_before_destroy = true
  }
  security_group_id = aws_security_group.efs.id
  type              = "egress"
  from_port         = 0
  to_port           = 65535
  cidr_blocks       = ["0.0.0.0/0"]
  ipv6_cidr_blocks  = ["::/0"]
  protocol          = "all"
}

resource "aws_security_group_rule" "efs_inbound" {
  for_each = {
    "Admin"       = aws_security_group.AdminNode.id,
    "Compilation" = aws_security_group.CompilerExplorer.id
    "Builder"     = aws_security_group.Builder.id
    "CI-x64"      = "sg-07a8509aae61cbe4f"
    "CI-arm64"    = "sg-0d3a3411b05a2bfb4"
  }
  security_group_id        = aws_security_group.efs.id
  type                     = "ingress"
  from_port                = 0
  to_port                  = 65535
  protocol                 = "all"
  source_security_group_id = each.value
  description              = "${each.key} node acccess"
}

resource "aws_iam_user" "github" {
  name = "github"
}

resource "aws_iam_user_policy_attachment" "github_attach_CeBuilderStorageAccess" {
  user       = aws_iam_user.github.name
  policy_arn = aws_iam_policy.CeBuilderStorageAccess.arn
}

resource "aws_iam_role" "CompilerExplorerAdminNode" {
  name               = "CompilerExplorerAdminNode"
  description        = "Compiler Explorer admin node role"
  assume_role_policy = data.aws_iam_policy_document.InstanceAssumeRolePolicy.json
}

resource "aws_iam_instance_profile" "CompilerExplorerAdminNode" {
  name = "CompilerExplorerAdminNode"
  role = aws_iam_role.CompilerExplorerAdminNode.name
}

data "aws_iam_policy" "CloudWatchAgentAdminPolicy" {
  arn = "arn:aws:iam::052730242331:policy/CloudWatchAgentAdminPolicy"
}

resource "aws_iam_role_policy_attachment" "CompilerExplorerAdminNode_attach_CloudWatchAgentServerPolicy" {
  role       = aws_iam_role.CompilerExplorerAdminNode.name
  policy_arn = data.aws_iam_policy.CloudWatchAgentAdminPolicy.arn
}

resource "aws_iam_role_policy_attachment" "CompilerExplorerAdminNode_attach_managed" {
  for_each = {
    "AmazonEC2FullAccess" : true,
    "AmazonS3FullAccess" : true,
    "CloudWatchFullAccess" : true,
    "AmazonDynamoDBFullAccess" : true,
    "service-role/AWSQuicksightAthenaAccess" : true,
    "CloudFrontFullAccess" : true,
  }
  role       = aws_iam_role.CompilerExplorerAdminNode.name
  policy_arn = "arn:aws:iam::aws:policy/${each.key}"
}

/* API Gateway Logging */

data "aws_iam_policy_document" "api_gw_trust_policy" {
  statement {
    actions = ["sts:AssumeRole"]
    effect  = "Allow"
    principals {
      type        = "Service"
      identifiers = ["apigateway.amazonaws.com", "lambda.amazonaws.com"]
    }
  }
}

/* note: this role is manually attached to API Gateway under Settings -> Logging -> CloudWatch log role ARN, it cannot be set via TF */
resource "aws_iam_role" "iam_for_apigw" {
  name               = "iam_for_apigw"
  assume_role_policy = data.aws_iam_policy_document.api_gw_trust_policy.json
}

resource "aws_iam_role_policy_attachment" "api_gw_logging_policy" {
  role       = aws_iam_role.iam_for_apigw.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonAPIGatewayPushToCloudWatchLogs"
}


# note: SG mentioned here is created by the ce-ci terraform

resource "aws_security_group_rule" "WinBuilder_SmbLocally" {
  security_group_id        = aws_security_group.CompilerExplorer.id
  type                     = "ingress"
  from_port                = 445
  to_port                  = 445
  source_security_group_id = "sg-06f4355d49a1e117b"
  protocol                 = "tcp"
  description              = "Allow SMB access locally"
}

# note: roles mentioned here are applied by the ce-ci terraform, so comment this out if that is not applied yet
resource "aws_iam_instance_profile" "WinBuilder" {
  name = "WinBuilder"
  role = "ce-ci-windows-x64-win-builder-runner-role"
}

resource "aws_iam_role_policy_attachment" "WinBuilder_attach_UpdateLibraryBuildHistory" {
  role       = "ce-ci-windows-x64-win-builder-runner-role"
  policy_arn = aws_iam_policy.UpdateLibraryBuildHistory.arn
}

resource "aws_iam_role_policy_attachment" "WinBuilder_attach_AccessCeParams" {
  role       = "ce-ci-windows-x64-win-builder-runner-role"
  policy_arn = aws_iam_policy.AccessCeParams.arn
}

resource "aws_iam_role_policy_attachment" "WinBuilder_attach_ReadS3Minimal" {
  role       = "ce-ci-windows-x64-win-builder-runner-role"
  policy_arn = aws_iam_policy.ReadS3Minimal.arn
}

resource "aws_iam_role_policy_attachment" "WinBuilder_attach_AmazonSSMManagedInstanceCore" {
  role       = "ce-ci-windows-x64-win-builder-runner-role"
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}
