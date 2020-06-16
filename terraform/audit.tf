data "aws_caller_identity" "current" {}

resource "aws_cloudtrail" "audit" {
  name                          = "ce-audit"
  s3_bucket_name                = aws_s3_bucket.cloudtrail.id
  include_global_service_events = true
  tags                          = {
    Site = "CompilerExplorer"
  }
  event_selector {
    include_management_events = true
  }
  is_multi_region_trail         = true
  enable_log_file_validation    = true
}

data "aws_iam_policy_document" "audit-s3-policy" {
  statement {
    principals {
      type        = "Service"
      identifiers = ["cloudtrail.amazonaws.com"]
    }
    sid       = "AWSCloudTrailAclCheck"
    actions   = ["s3:GetBucketAcl"]
    resources = [aws_s3_bucket.cloudtrail.arn]
  }
  statement {
    sid       = "AWSCloudTrailWrite"
    principals {
      type        = "Service"
      identifiers = ["cloudtrail.amazonaws.com"]
    }
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.cloudtrail.arn}/AWSLogs/${data.aws_caller_identity.current.account_id}/*"]
    condition {
      test     = "StringEquals"
      variable = "s3:x-amz-acl"
      values   = ["bucket-owner-full-control"]
    }
  }
}

resource "aws_s3_bucket" "cloudtrail" {
  bucket        = "cloudtrail.godbolt.org"
  force_destroy = true

  // TODO one day
  //  versioning {
  //    mfa_delete = true
  //  }

  lifecycle_rule {
    enabled = true
    expiration {
      days = 200
    }
    noncurrent_version_expiration {
      days = 1
    }
  }
}

resource "aws_s3_bucket_policy" "cloudtrail-bucket-policy" {
  bucket = aws_s3_bucket.cloudtrail.id
  policy = data.aws_iam_policy_document.audit-s3-policy.json
}