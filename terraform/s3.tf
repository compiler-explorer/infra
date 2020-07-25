resource "aws_s3_bucket" "compiler-explorer" {
  bucket = "compiler-explorer"
  acl    = "private"
  tags   = {
    Site = "CompilerExplorer"
  }
  cors_rule {
    allowed_headers = ["Authorization"]
    allowed_methods = ["GET"]
    allowed_origins = ["*"]
    max_age_seconds = 3000
  }
  # Keep only one month (rounding down) of cloudfront logs (See the privacy policy in the compiler explorer project)
  lifecycle_rule {
    enabled = true
    expiration {
      days = 28
    }
    noncurrent_version_expiration {
      days = 1
    }
    # Covers both cloudfront-logs and cloudfront-logs-ce:
    prefix  = "cloudfront-logs"
  }
}

resource "aws_s3_bucket" "compiler-explorer-logs" {
  bucket = "compiler-explorer-logs"
  tags   = {
    Site = "CompilerExplorer"
  }

  # not sure if we explicitly need to state the bucket owner gets full control
  # when `acl = private` is not stated, but better safe than sorry
  grant {
    id          = data.aws_caller_identity.current.account_id
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

  # Keep only one month of elb logs (See the privacy policy in the compiler explorer project)
  lifecycle_rule {
    enabled = true
    expiration {
      days = 32
    }
    noncurrent_version_expiration {
      days = 1
    }
    prefix  = "elb/"
  }

  # Keep only one month of cloudfront logs (See the privacy policy in the compiler explorer project)
  lifecycle_rule {
    enabled = true
    expiration {
      days = 32
    }
    noncurrent_version_expiration {
      days = 1
    }
    prefix  = "cloudfront/"
  }
}

data "aws_billing_service_account" "main" {}

data "aws_iam_policy_document" "compiler-explorer-s3-policy" {
  // Allow external (public) access to certain directories on S3
  statement {
    sid       = "PublicReadGetObjects"
    actions   = ["s3:GetObject"]
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
    sid       = "Allow listing of bucket (NB allows listing everything)"
    actions   = ["s3:ListBucket"]
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
    actions   = [
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

resource "aws_s3_bucket" "opt-s3-godbolt-org" {
  bucket = "opt-s3.godbolt.org"
  acl    = "private"
  tags   = {
    Site = "CompilerExplorer"
  }
}

resource "aws_s3_bucket" "storage-godbolt-org" {
  bucket = "storage.godbolt.org"
  acl    = "private"
  tags   = {
    Site = "CompilerExplorer"
  }
  lifecycle_rule {
    enabled                                = true
    abort_incomplete_multipart_upload_days = 7
    expiration {
      days = 1
    }
    noncurrent_version_expiration {
      days = 1
    }
    prefix                                 = "cache/"
  }
}

resource "aws_s3_bucket" "ce-cdn-net" {
  bucket = "ce-cdn.net"
  acl    = "private"
  tags   = {
    Site = "CompilerExplorer"
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
    sid       = "PublicReadGetObjects"
    actions   = ["s3:GetObject"]
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
