locals {
  temp_storage_bucket_name    = "temp-storage.godbolt.org"
  temp_storage_retention_days = var.temp_storage_retention_days

  temp_storage_common_tags = {
    Service   = "CompilerExplorer"
    Component = "TempStorage"
    ManagedBy = "Terraform"
    Purpose   = "Temporary storage for various services"
  }
}

resource "aws_s3_bucket" "temp_storage" {
  bucket = local.temp_storage_bucket_name

  tags = merge(
    local.temp_storage_common_tags,
    {
      Name = local.temp_storage_bucket_name
    }
  )

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_versioning" "temp_storage" {
  bucket = aws_s3_bucket.temp_storage.id

  versioning_configuration {
    status = "Disabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "temp_storage" {
  bucket = aws_s3_bucket.temp_storage.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "temp_storage" {
  bucket = aws_s3_bucket.temp_storage.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "temp_storage" {
  bucket = aws_s3_bucket.temp_storage.id

  rule {
    id     = "delete_old_overflow_messages"
    status = "Enabled"

    expiration {
      days = local.temp_storage_retention_days
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

resource "aws_s3_bucket_policy" "temp_storage" {
  bucket = aws_s3_bucket.temp_storage.id
  policy = data.aws_iam_policy_document.temp_storage_bucket_policy.json
}

data "aws_iam_policy_document" "temp_storage_bucket_policy" {
  statement {
    sid    = "DenyInsecureTransport"
    effect = "Deny"

    principals {
      type        = "AWS"
      identifiers = ["*"]
    }

    actions = ["s3:*"]

    resources = [
      aws_s3_bucket.temp_storage.arn,
      "${aws_s3_bucket.temp_storage.arn}/*"
    ]

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

data "aws_iam_policy_document" "temp_storage_sqs_overflow_access" {
  statement {
    sid = "OverflowBucketWrite"

    actions = [
      "s3:PutObject",
      "s3:PutObjectTagging"
    ]

    resources = [
      "${aws_s3_bucket.temp_storage.arn}/sqs-overflow/*"
    ]
  }

  statement {
    sid = "OverflowBucketRead"

    actions = [
      "s3:GetObject",
      "s3:GetObjectTagging"
    ]

    resources = [
      "${aws_s3_bucket.temp_storage.arn}/sqs-overflow/*"
    ]
  }

  statement {
    sid = "OverflowBucketList"

    actions = [
      "s3:ListBucket"
    ]

    resources = [
      aws_s3_bucket.temp_storage.arn
    ]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["sqs-overflow/*"]
    }
  }
}

resource "aws_iam_policy" "temp_storage_sqs_overflow_access" {
  name        = "temp-storage-sqs-overflow-access"
  description = "Allow services to read/write SQS overflow messages in temp storage"
  policy      = data.aws_iam_policy_document.temp_storage_sqs_overflow_access.json
}

resource "aws_iam_role_policy_attachment" "lambda_temp_storage_sqs_overflow" {
  role       = aws_iam_role.iam_for_lambda.name
  policy_arn = aws_iam_policy.temp_storage_sqs_overflow_access.arn
}

resource "aws_iam_role_policy_attachment" "ce_router_temp_storage_sqs_overflow" {
  role       = aws_iam_role.CeRouterRole.name
  policy_arn = aws_iam_policy.temp_storage_sqs_overflow_access.arn
}

resource "aws_iam_role_policy_attachment" "compiler_explorer_temp_storage_sqs_overflow" {
  role       = aws_iam_role.CompilerExplorerRole.name
  policy_arn = aws_iam_policy.temp_storage_sqs_overflow_access.arn
}

resource "aws_iam_role_policy_attachment" "compiler_explorer_windows_temp_storage_sqs_overflow" {
  role       = aws_iam_role.CompilerExplorerWindowsRole.name
  policy_arn = aws_iam_policy.temp_storage_sqs_overflow_access.arn
}


output "temp_storage_bucket_name" {
  value       = aws_s3_bucket.temp_storage.id
  description = "Name of the temp storage S3 bucket"
}

output "temp_storage_bucket_arn" {
  value       = aws_s3_bucket.temp_storage.arn
  description = "ARN of the temp storage S3 bucket"
}

output "temp_storage_sqs_overflow_policy_arn" {
  value       = aws_iam_policy.temp_storage_sqs_overflow_access.arn
  description = "ARN of the IAM policy for temp storage SQS overflow access"
}
