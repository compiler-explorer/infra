resource "aws_iam_role" "elfshaker" {
  name               = "elfshaker"
  assume_role_policy = data.aws_iam_policy_document.aws_lambda_trust_policy.json
}

# Should grant logging etc
resource "aws_iam_role_policy_attachment" "elfshaker_basic_lambda" {
  role       = aws_iam_role.elfshaker.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_cloudwatch_log_group" "elfshaker" {
  name              = "/aws/lambda/elfshaker"
  retention_in_days = 14
}

resource "aws_s3_bucket" "elfshaker-godbolt-org" {
  bucket = "elfshaker.godbolt.org"
  tags = {
    S3-Bucket-Name = "elfshaker.godbolt.org"
  }
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_ownership_controls" "elfshaker-godbolt-org" {
  bucket = aws_s3_bucket.elfshaker-godbolt-org.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

# Probably need to set this up to _allow_ public access
resource "aws_s3_bucket_public_access_block" "elfshaker-godbolt-org" {
  bucket = aws_s3_bucket.elfshaker-godbolt-org.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# resource "aws_s3_bucket_lifecycle_configuration" "elfshaker-godbolt-org" {
#   bucket = aws_s3_bucket.elfshaker-godbolt-org.id
#   rule {
#     id     = "Remove cached items"
#     status = "Enabled"
#     expiration {
#       days = 3
#     }
#     noncurrent_version_expiration {
#       noncurrent_days = 1
#     }
#     filter {
#       prefix = ""
#     }
#   }
# }

# IAM Policy for S3 Access
data "aws_iam_policy_document" "elfshaker_s3_access" {
  statement {
    sid = "ElfShakerS3"
    actions = [
      "s3:GetObject",
      "s3:PutObject"
    ]
    resources = ["${aws_s3_bucket.elfshaker-godbolt-org.arn}/*"]
  }
}

resource "aws_iam_policy" "elfshaker_s3_access" {
  name        = "elfshaker_lambda_s3_access"
  description = "Allow elfshaker lambda to access its s3 bucket"
  policy      = data.aws_iam_policy_document.elfshaker_s3_access.json
}

resource "aws_iam_role_policy_attachment" "elfshaker_s3_access" {
  role       = aws_iam_role.elfshaker.name
  policy_arn = aws_iam_policy.elfshaker_s3_access.arn
}
