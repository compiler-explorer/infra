locals {
  log_file_retention_days = 32  # One month, rounding up (See the privacy policy in the compiler explorer project)
}

resource "aws_s3_bucket" "compiler-explorer" {
  bucket = "compiler-explorer"
  acl    = "private"
  tags   = {
    S3-Bucket-Name = "compiler-explorer"
  }
  lifecycle {
    prevent_destroy = true
  }
  cors_rule {
    allowed_headers = ["Authorization"]
    allowed_methods = ["GET"]
    allowed_origins = ["*"]
    max_age_seconds = 3000
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "compiler-explorer" {
  bucket = aws_s3_bucket.compiler-explorer.id
  rule {
    id     = "delete_cloudfront_logs_per_log_policy"
    status = "Enabled"
    expiration {
      days = local.log_file_retention_days
    }
    noncurrent_version_expiration {
      noncurrent_days = 1
    }
    filter {
      # Covers both cloudfront-logs and cloudfront-logs-ce:
      prefix = "cloudfront-logs"
    }
  }
}

data "aws_canonical_user_id" "current" {}

resource "aws_s3_bucket" "compiler-explorer-logs" {
  bucket = "compiler-explorer-logs"
  tags   = {
    S3-Bucket-Name = "compiler-explorer-logs"
  }

  lifecycle {
    prevent_destroy = true
  }

  # not sure if we explicitly need to state the bucket owner gets full control
  # when `acl = private` is not stated, but better safe than sorry
  grant {
    id          = data.aws_canonical_user_id.current.id
    type        = "CanonicalUser"
    permissions = ["FULL_CONTROL"]
  }

  # awslogsdelivery account needs full control for cloudfront logging
  # https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/AccessLogs.html
  grant {
    id          = "c4c1ede66af53448b93c283ce9448c4ba468c9432aa01d700d3878632f77d2d0"
    type        = "CanonicalUser"
    permissions = ["FULL_CONTROL"]
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "compiler-explorer-logs" {
  bucket = aws_s3_bucket.compiler-explorer-logs.id
  dynamic "rule" {
    # Keep only one month of these logs (See the privacy policy in the compiler explorer project)
    for_each = {
      cloudfront = "cloudfront"
      elb        = "elb"
    }
    content {
      id     = "delete_${rule.value}_per_log_policy"
      status = "Enabled"
      expiration {
        days = local.log_file_retention_days
      }
      noncurrent_version_expiration {
        noncurrent_days = 1
      }
      filter {
        prefix = "${rule.value}/"
      }
    }
  }
}

data "aws_billing_service_account" "main" {}

data "aws_iam_policy_document" "compiler-explorer-s3-policy" {
  // Allow external (public) access to certain directories on S3
  statement {
    sid     = "PublicReadGetObjects"
    actions = ["s3:GetObject"]
    principals {
      identifiers = ["*"]
      type        = "*"
    }
    resources = [
      "${aws_s3_bucket.compiler-explorer.arn}/opt/*",
      "${aws_s3_bucket.compiler-explorer.arn}/admin/*"
    ]
  }
  statement {
    sid     = "Allow listing of bucket (NB allows listing everything)"
    actions = ["s3:ListBucket"]
    principals {
      identifiers = ["*"]
      type        = "*"
    }
    resources = [aws_s3_bucket.compiler-explorer.arn]
  }

  // AWS billing statements
  statement {
    principals {
      identifiers = [data.aws_billing_service_account.main.arn]
      type        = "AWS"
    }
    actions = [
      "s3:GetBucketAcl",
      "s3:GetBucketPolicy"
    ]
    resources = [aws_s3_bucket.compiler-explorer.arn]
  }
  statement {
    principals {
      identifiers = [data.aws_billing_service_account.main.arn]
      type        = "AWS"
    }
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.compiler-explorer.arn}/*"]
  }
}

data "aws_iam_policy_document" "compiler-explorer-logs-s3-policy" {
  statement {
    principals {
      // see https://docs.aws.amazon.com/elasticloadbalancing/latest/application/load-balancer-access-logs.html#access-logging-bucket-permissions
      identifiers = ["arn:aws:iam::127311923021:root"]
      type        = "AWS"
    }
    sid       = "Allow ELB to write logs"
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.compiler-explorer-logs.arn}/elb/*"]
  }
}

resource "aws_s3_bucket_policy" "compiler-explorer" {
  bucket = aws_s3_bucket.compiler-explorer.id
  policy = data.aws_iam_policy_document.compiler-explorer-s3-policy.json
}

resource "aws_s3_bucket_policy" "compiler-explorer-logs" {
  bucket = aws_s3_bucket.compiler-explorer-logs.id
  policy = data.aws_iam_policy_document.compiler-explorer-logs-s3-policy.json
}

resource "aws_s3_bucket" "storage-godbolt-org" {
  bucket = "storage.godbolt.org"
  acl    = "private"
  tags   = {
    S3-Bucket-Name = "storage.godbolt.org"
  }
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "storage-godbolt-org" {
  bucket = aws_s3_bucket.storage-godbolt-org.id
  rule {
    id     = "Remove cached items"
    status = "Enabled"
    expiration {
      days = 1
    }
    noncurrent_version_expiration {
      noncurrent_days = 1
    }
    filter {
      prefix = "cache/"
    }
  }
}

resource "aws_s3_bucket" "ce-cdn-net" {
  bucket = "ce-cdn.net"
  acl    = "private"
  tags   = {
    S3-Bucket-Name = "ce-cdn.net"
  }
  lifecycle {
    prevent_destroy = true
  }
  cors_rule {
    allowed_methods = ["GET"]
    allowed_origins = ["*"]
  }

  versioning {
    enabled = true
  }
}

data "aws_iam_policy_document" "ce-cdn-net-s3-policy" {
  statement {
    sid     = "PublicReadGetObjects"
    actions = ["s3:GetObject"]
    principals {
      identifiers = ["*"]
      type        = "*"
    }
    resources = ["${aws_s3_bucket.ce-cdn-net.arn}/*"]
  }
}

resource "aws_s3_bucket_policy" "ce-cdn-net" {
  bucket = aws_s3_bucket.ce-cdn-net.id
  policy = data.aws_iam_policy_document.ce-cdn-net-s3-policy.json
}
