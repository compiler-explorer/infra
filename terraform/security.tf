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

resource "aws_security_group_rule" "ALB_IngressFromCE" {
  security_group_id = "${aws_security_group.CompilerExplorerAlb.id}"
  type = "ingress"
  from_port = 0
  to_port = 65535
  source_security_group_id = "${aws_security_group.CompilerExplorer.id}"
  protocol = "tcp"
  description = "Allow ingress from CE nodes"
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

resource "aws_security_group_rule" "Admin_IngressFromCE" {
  security_group_id = "${aws_security_group.AdminNode.id}"
  type = "egress"
  from_port = 0
  to_port = 65535
  source_security_group_id = "${aws_security_group.CompilerExplorer.id}"
  protocol = "tcp"
  description = "Allow ingress from CE nodes"
}

resource "aws_iam_role" "CompilerExplorerRole" {
  name = "CompilerExplorerRole"
  description = "Compiler Explorer node role"
  assume_role_policy = <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Action": "sts:AssumeRole",
      "Principal": {
        "Service": "ec2.amazonaws.com"
      },
      "Effect": "Allow",
      "Sid": ""
    }
  ]
}
EOF

  tags {
    "Site" = "CompilerExplorer"
  }
}

data "aws_iam_policy" "CloudWatchAgentServerPolicy" {
  arn = "arn:aws:iam::052730242331:policy/CloudWatchAgentServerPolicy"
}

resource "aws_iam_policy" "CeModifyStoredState" {
  name = "CeModifyStoredState"
  description = "Can create and list short links for compiler explorer"
  policy = <<EOF
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "DatabaseAccessSid",
            "Effect": "Allow",
            "Action": [
                "dynamodb:PutItem",
                "dynamodb:UpdateItem",
                "dynamodb:DescribeTable",
                "dynamodb:GetItem",
                "dynamodb:Scan",
                "dynamodb:Query"
            ],
            "Resource": "${aws_dynamodb_table.links.arn}"
        },
        {
            "Sid": "S3AccessSid",
            "Effect": "Allow",
            "Action": "s3:*",
            "Resource": [
                "${aws_s3_bucket.storage-godbolt-org.arn}/*",
                "${aws_s3_bucket.storage-godbolt-org.arn}"
            ]
        }
    ]
}
EOF
}

resource "aws_iam_policy" "AccessCeParams" {
  name = "AccessCeParams"
  description = "Can read Compiler Explorer parameters/secrets"
  policy = <<EOF
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "ssm:Describe*",
                "ssm:Get*",
                "ssm:List*"
            ],
            "Resource": "arn:aws:ssm:us-east-1:052730242331:parameter/compiler-explorer/*"
        }
    ]
}
EOF
}

resource "aws_iam_policy" "ReadS3Minimal" {
  name = "ReadS3Minimal"
  description = "Minimum possible read acces to S3 to boot an instance"
  policy = <<EOF
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "s3:Get*"
            ],
            "Resource": [
                "${aws_s3_bucket.compiler-explorer.arn}/authorized_keys/*",
                "${aws_s3_bucket.compiler-explorer.arn}/version/*"
            ]
        }
    ]
}
EOF
}

resource "aws_iam_instance_profile" "CompilerExplorerRole" {
  name = "CompilerExplorerRole"
  role = "${aws_iam_role.CompilerExplorerRole.name}"
}

resource "aws_iam_role_policy_attachment" "CompilerExplorerRole_attach_CloudWatchAgentServerPolicy" {
  role = "${aws_iam_role.CompilerExplorerRole.name}"
  policy_arn = "${data.aws_iam_policy.CloudWatchAgentServerPolicy.arn}"
}

resource "aws_iam_role_policy_attachment" "CompilerExplorerRole_attach_CeModifyStoredState" {
  role = "${aws_iam_role.CompilerExplorerRole.name}"
  policy_arn = "${aws_iam_policy.CeModifyStoredState.arn}"
}

resource "aws_iam_role_policy_attachment" "CompilerExplorerRole_attach_AccessCeParams" {
  role = "${aws_iam_role.CompilerExplorerRole.name}"
  policy_arn = "${aws_iam_policy.AccessCeParams.arn}"
}

resource "aws_iam_role_policy_attachment" "CompilerExplorerRole_attach_ReadS3Minimal" {
  role = "${aws_iam_role.CompilerExplorerRole.name}"
  policy_arn = "${aws_iam_policy.ReadS3Minimal.arn}"
}
