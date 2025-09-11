locals {
  overflow_bucket_name    = "compiler-explorer-sqs-overflow"
  overflow_retention_days = var.sqs_overflow_retention_days

  overflow_common_tags = {
    Service   = "CompilerExplorer"
    Component = "SQSOverflow"
    ManagedBy = "Terraform"
    Purpose   = "Store large SQS messages"
  }
}

resource "aws_s3_bucket" "sqs_overflow" {
  bucket = local.overflow_bucket_name

  tags = merge(
    local.overflow_common_tags,
    {
      Name = local.overflow_bucket_name
    }
  )

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_versioning" "sqs_overflow" {
  bucket = aws_s3_bucket.sqs_overflow.id

  versioning_configuration {
    status = "Disabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "sqs_overflow" {
  bucket = aws_s3_bucket.sqs_overflow.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "sqs_overflow" {
  bucket = aws_s3_bucket.sqs_overflow.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "sqs_overflow" {
  bucket = aws_s3_bucket.sqs_overflow.id

  rule {
    id     = "delete_old_overflow_messages"
    status = "Enabled"

    expiration {
      days = local.overflow_retention_days
    }

    filter {
      prefix = ""
    }
  }

  rule {
    id     = "cleanup_incomplete_uploads"
    status = "Enabled"

    abort_incomplete_multipart_upload {
      days_after_initiation = 1
    }

    filter {
      prefix = ""
    }
  }
}

resource "aws_s3_bucket_policy" "sqs_overflow" {
  bucket = aws_s3_bucket.sqs_overflow.id
  policy = data.aws_iam_policy_document.sqs_overflow_bucket_policy.json
}

data "aws_iam_policy_document" "sqs_overflow_bucket_policy" {
  statement {
    sid    = "DenyInsecureTransport"
    effect = "Deny"

    principals {
      type        = "AWS"
      identifiers = ["*"]
    }

    actions = ["s3:*"]

    resources = [
      aws_s3_bucket.sqs_overflow.arn,
      "${aws_s3_bucket.sqs_overflow.arn}/*"
    ]

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

data "aws_iam_policy_document" "sqs_overflow_access" {
  statement {
    sid = "OverflowBucketWrite"

    actions = [
      "s3:PutObject",
      "s3:PutObjectTagging"
    ]

    resources = [
      "${aws_s3_bucket.sqs_overflow.arn}/messages/*"
    ]
  }

  statement {
    sid = "OverflowBucketRead"

    actions = [
      "s3:GetObject",
      "s3:GetObjectTagging"
    ]

    resources = [
      "${aws_s3_bucket.sqs_overflow.arn}/messages/*"
    ]
  }

  statement {
    sid = "OverflowBucketList"

    actions = [
      "s3:ListBucket"
    ]

    resources = [
      aws_s3_bucket.sqs_overflow.arn
    ]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["messages/*"]
    }
  }
}

resource "aws_iam_policy" "sqs_overflow_access" {
  name        = "sqs-overflow-s3-access"
  description = "Allow services to read/write SQS overflow messages in S3"
  policy      = data.aws_iam_policy_document.sqs_overflow_access.json
}

resource "aws_iam_role_policy_attachment" "lambda_sqs_overflow" {
  role       = aws_iam_role.iam_for_lambda.name
  policy_arn = aws_iam_policy.sqs_overflow_access.arn
}

resource "aws_iam_role_policy_attachment" "ce_router_sqs_overflow" {
  role       = aws_iam_role.CeRouterRole.name
  policy_arn = aws_iam_policy.sqs_overflow_access.arn
}

resource "aws_iam_role_policy_attachment" "compiler_explorer_sqs_overflow" {
  role       = aws_iam_role.CompilerExplorerRole.name
  policy_arn = aws_iam_policy.sqs_overflow_access.arn
}

resource "aws_iam_role_policy_attachment" "compiler_explorer_windows_sqs_overflow" {
  role       = aws_iam_role.CompilerExplorerWindowsRole.name
  policy_arn = aws_iam_policy.sqs_overflow_access.arn
}

resource "aws_cloudwatch_log_metric_filter" "sqs_overflow_usage" {
  name           = "sqs-overflow-messages"
  log_group_name = "/aws/lambda/compilation"
  pattern        = "[time, request_id, level = INFO, msg = \"Message size * exceeds limit * storing in S3\"]"

  metric_transformation {
    name      = "SQSOverflowMessages"
    namespace = "CompilerExplorer/SQSOverflow"
    value     = "1"
    unit      = "Count"
  }
}

resource "aws_cloudwatch_metric_alarm" "sqs_overflow_high_usage" {
  alarm_name          = "sqs-overflow-high-usage"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "SQSOverflowMessages"
  namespace           = "CompilerExplorer/SQSOverflow"
  period              = "300"
  statistic           = "Sum"
  threshold           = "100"
  alarm_description   = "Alert when SQS overflow usage is high"
  treat_missing_data  = "notBreaching"

  alarm_actions = [data.aws_sns_topic.alert.arn]
}

output "sqs_overflow_bucket_name" {
  value       = aws_s3_bucket.sqs_overflow.id
  description = "Name of the S3 bucket for SQS overflow messages"
}

output "sqs_overflow_bucket_arn" {
  value       = aws_s3_bucket.sqs_overflow.arn
  description = "ARN of the S3 bucket for SQS overflow messages"
}

output "sqs_overflow_policy_arn" {
  value       = aws_iam_policy.sqs_overflow_access.arn
  description = "ARN of the IAM policy for SQS overflow access"
}