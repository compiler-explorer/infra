resource "aws_s3_bucket" "compiler-explorer" {
  bucket = "compiler-explorer"
  acl    = "private"
  tags {
    Site = "CompilerExplorer"
  }
  cors_rule {
    allowed_headers = ["Authorization"]
    allowed_methods = ["GET"]
    allowed_origins = ["*"]
    max_age_seconds = 3000
  }
  # Keep only five years of cloudfront logs (See the privacy policy in the compiler explorer project)
  lifecycle_rule {
    enabled = true
    expiration {
      days = 32
    }
    noncurrent_version_expiration {
      days = 1
    }
    # Covers both cloudfront-logs and cloudfront-logs-ce:
    prefix  = "cloudfront-logs"
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
    resources = ["${aws_s3_bucket.compiler-explorer.arn}"]
  }

  // AWS billing statements
  statement {
    principals {
      identifiers = ["${data.aws_billing_service_account.main.arn}"]
      type        = "AWS"
    }
    actions   = [
      "s3:GetBucketAcl",
      "s3:GetBucketPolicy"
    ]
    resources = ["${aws_s3_bucket.compiler-explorer.arn}"]
  }
  statement {
    principals {
      identifiers = ["${data.aws_billing_service_account.main.arn}"]
      type        = "AWS"
    }
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.compiler-explorer.arn}/*"]
  }
}

resource "aws_s3_bucket_policy" "compiler-explorer" {
  bucket = "${aws_s3_bucket.compiler-explorer.id}"
  policy = "${data.aws_iam_policy_document.compiler-explorer-s3-policy.json}"
}

resource "aws_s3_bucket" "opt-s3-godbolt-org" {
  bucket = "opt-s3.godbolt.org"
  acl    = "private"
  tags {
    Site = "CompilerExplorer"
  }
}

resource "aws_s3_bucket" "storage-godbolt-org" {
  bucket = "storage.godbolt.org"
  acl    = "private"
  tags {
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
