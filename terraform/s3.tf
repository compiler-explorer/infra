resource "aws_s3_bucket" "compiler-explorer" {
  bucket = "compiler-explorer"
  acl = "private"
  tags {
    Site = "CompilerExplorer"
  }
  cors_rule {
    allowed_headers = [
      "Authorization"
    ]
    allowed_methods = [
      "GET"
    ]
    allowed_origins = [
      "*"
    ]
    max_age_seconds = 3000
  }
  # Keep only five years of cloudfront logs (See the privacy policy in the compiler explorer project)
  lifecycle_rule {
    enabled = true
    expiration {
      days = 1
    }
    noncurrent_version_expiration {
      days = 1825 # 5 years
    }
    # Covers both cloudfront-logs and cloudfront-logs-ce:
    prefix = "cloudfront-logs"
  }
}

resource "aws_s3_bucket_policy" "compiler-explorer" {
  bucket = "${aws_s3_bucket.compiler-explorer.id}"
  policy = <<POLICY
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "PublicReadGetObject",
      "Effect": "Allow",
      "Principal": "*",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::compiler-explorer/opt/*"
    },
    {
      "Sid": "PublicReadGetObjectForAdmin",
      "Effect": "Allow",
      "Principal": "*",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::compiler-explorer/admin/*"
    },
    {
      "Sid": "Allow listing of bucket (NB allows listing everything)",
      "Effect": "Allow",
      "Principal": "*",
      "Action": "s3:ListBucket",
      "Resource": "arn:aws:s3:::compiler-explorer"
    },
    {
      "Sid": "Stmt1335892150622",
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::386209384616:root"
      },
      "Action": [
        "s3:GetBucketAcl",
        "s3:GetBucketPolicy"
      ],
      "Resource": "arn:aws:s3:::compiler-explorer"
    },
    {
      "Sid": "Stmt1335892526596",
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::386209384616:root"
      },
      "Action": "s3:PutObject",
      "Resource": "arn:aws:s3:::compiler-explorer/*"
    }
  ]
}
POLICY
}

resource "aws_s3_bucket" "opt-s3-godbolt-org" {
  bucket = "opt-s3.godbolt.org"
  acl = "private"
  tags {
    Site = "CompilerExplorer"
  }
}

resource "aws_s3_bucket" "storage-godbolt-org" {
  bucket = "storage.godbolt.org"
  acl = "private"
  tags {
    Site = "CompilerExplorer"
  }
  lifecycle_rule {
    enabled = true
    abort_incomplete_multipart_upload_days = 7
    expiration {
      days = 1
    }
    noncurrent_version_expiration {
      days = 1
    }
    prefix = "cache/"
  }
}
