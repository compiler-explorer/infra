resource "aws_iam_role" "compiler-build-service-role" {
  name = "codebuild-compiler-build-service-role"
  path = "/service-role/"
  assume_role_policy = <<POLICY
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "codebuild.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
POLICY
}

resource "aws_iam_role_policy" "compiler-build-service-policy" {
  role = "${aws_iam_role.compiler-build-service-role.name}"

  policy = <<POLICY
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Resource": [
        "*"
      ],
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "ec2:CreateNetworkInterface",
        "ec2:DescribeDhcpOptions",
        "ec2:DescribeNetworkInterfaces",
        "ec2:DeleteNetworkInterface",
        "ec2:DescribeSubnets",
        "ec2:DescribeSecurityGroups",
        "ec2:DescribeVpcs"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "s3:*"
      ],
      "Resource": [
        "${aws_s3_bucket.compiler-explorer.arn}",
        "${aws_s3_bucket.compiler-explorer.arn}/*"
      ]
    }
  ]
}
POLICY
}

resource "aws_codebuild_project" "build-compilers" {
  name = "build-compilers"
  description = "Build compilers from a docker image"
  build_timeout = "120"
  service_role = "${aws_iam_role.compiler-build-service-role.arn}"

  artifacts {
    type = "S3"
    location = "${aws_s3_bucket.compiler-explorer.bucket}"
    packaging = "NONE"
    path = ""
    name = "test-artifacts"
    namespace_type = "NONE"
  }

  source {
    type = "NO_SOURCE"
    buildspec = "${file("build-compilers.yaml")}"
  }

  environment {
    compute_type = "BUILD_GENERAL1_LARGE"
    image = "aws/codebuild/docker:17.09.0"
    type = "LINUX_CONTAINER"
    privileged_mode = true

    environment_variable {
      "name" = "IMAGE"
      "value" = "gcc"
    }

    environment_variable {
      name = "COMMAND"
      value = "build.sh"
    }

    environment_variable {
      "name" = "VERSION"
      "value" = "trunk"
    }
  }

  tags {
    "Site" = "CompilerExplorer"
  }
}