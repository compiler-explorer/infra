locals {
  log_file_retention_days          = 32 # One month, rounding up (See the privacy policy in the compiler explorer project)
  log_file_longterm_retention_days = 365
}

resource "aws_s3_bucket" "compiler-explorer" {
  bucket = "compiler-explorer"
  tags = {
    S3-Bucket-Name = "compiler-explorer"
  }
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_versioning" "compiler-explorer" {
  bucket = aws_s3_bucket.compiler-explorer.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_acl" "compiler-explorer" {
  bucket = aws_s3_bucket.compiler-explorer.id
  acl    = "private"
}

resource "aws_s3_bucket_cors_configuration" "compiler-explorer" {
  bucket = aws_s3_bucket.compiler-explorer.id
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
      # Covers both cloudfront-logs and cloudfront-logs-ce:ami-020e4e9b0f0fecb06
      prefix = "cloudfront-logs"
    }
  }

  rule {
    id     = "expire_deleted_files"
    status = "Enabled"
    noncurrent_version_expiration {
      noncurrent_days = 7
    }
    filter {
      prefix = ""
    }
  }
}

data "aws_canonical_user_id" "current" {}

resource "aws_s3_bucket" "compiler-explorer-logs" {
  bucket = "compiler-explorer-logs"
  tags = {
    S3-Bucket-Name = "compiler-explorer-logs"
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_acl" "compiler-explorer-logs" {
  bucket = aws_s3_bucket.compiler-explorer-logs.id
  access_control_policy {
    owner {
      id = data.aws_canonical_user_id.current.id
    }

    grant {
      grantee {
        id   = data.aws_canonical_user_id.current.id
        type = "CanonicalUser"
      }
      permission = "FULL_CONTROL"
    }

    # awslogsdelivery account needs full control for cloudfront logging
    # https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/AccessLogs.html
    grant {
      grantee {
        id   = "c4c1ede66af53448b93c283ce9448c4ba468c9432aa01d700d3878632f77d2d0"
        type = "CanonicalUser"
      }
      permission = "FULL_CONTROL"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "compiler-explorer-logs" {
  bucket = aws_s3_bucket.compiler-explorer-logs.id
  dynamic "rule" {
    # Keep only one month of these logs (See the privacy policy in the compiler explorer project)
    for_each = {
      cloudfront   = "cloudfront"
      elb          = "elb"
      elb-internal = "elb-internal"
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

  dynamic "rule" {
    for_each = {
      compilestats = "compile-stats"
    }
    content {
      id     = "delete_${rule.value}_per_log_policy"
      status = "Enabled"
      expiration {
        days = local.log_file_longterm_retention_days
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
    sid     = "Allow ELB to write logs"
    actions = ["s3:PutObject"]
    resources = [
      "${aws_s3_bucket.compiler-explorer-logs.arn}/elb/*",
      "${aws_s3_bucket.compiler-explorer-logs.arn}/elb-internal/*"
    ]
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
  tags = {
    S3-Bucket-Name = "storage.godbolt.org"
  }
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_acl" "storage-godbolt-org" {
  bucket = aws_s3_bucket.storage-godbolt-org.id
  acl    = "private"
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
  tags = {
    S3-Bucket-Name = "ce-cdn.net"
  }
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_acl" "ce-cdn-net" {
  bucket = aws_s3_bucket.ce-cdn-net.id
  acl    = "private"
}

resource "aws_s3_bucket_versioning" "ce-cdn-net" {
  bucket = aws_s3_bucket.ce-cdn-net.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_cors_configuration" "ce-cdn-net" {
  bucket = aws_s3_bucket.ce-cdn-net.id
  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["GET"]
    allowed_origins = ["*"]
    max_age_seconds = 3600
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

resource "aws_glue_catalog_table" "compile_stats_table" {
  name          = "compile_stats"
  database_name = "default"

  table_type = "EXTERNAL_TABLE"

  parameters = {
    EXTERNAL = "TRUE"
  }

  partition_keys {
    name = "year"
    type = "int"
  }

  partition_keys {
    name = "month"
    type = "int"
  }

  partition_keys {
    name = "date"
    type = "int"
  }

  storage_descriptor {
    location      = "s3://compiler-explorer-logs/compile-stats"
    input_format  = "org.apache.hadoop.mapred.TextInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat"

    ser_de_info {
      serialization_library = "org.openx.data.jsonserde.JsonSerDe"

      parameters = {
        "serialization.format"  = 1
        "case.insensitive"      = "TRUE"
        "dots.in.keys"          = "FALSE"
        "ignore.malformed.json" = "FALSE"
        "mapping"               = "TRUE"
      }
    }

    columns {
      name = "time"
      type = "string"
    }

    columns {
      name = "compilerid"
      type = "string"
    }

    columns {
      name = "sourcehash"
      type = "string"
    }

    columns {
      name = "executionparamshash"
      type = "string"
    }

    columns {
      name = "bypasscache"
      type = "boolean"
    }

    columns {
      name = "options"
      type = "array<string>"
    }

    columns {
      name = "filters"
      type = "struct<binary:boolean,binaryobject:boolean,execute:boolean,demangle:boolean,intel:boolean,labels:boolean>"
    }

    columns {
      name = "backendoptions"
      type = "array<string>"
    }

    columns {
      name = "libraries"
      type = "array<string>"
    }

    columns {
      name = "tools"
      type = "array<string>"
    }

    columns {
      name = "overrides"
      type = "array<string>"
    }

    columns {
      name = "runtimetools"
      type = "array<string>"
    }

    columns {
      name = "buildmethod"
      type = "string"
    }
  }
}
