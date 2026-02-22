resource "random_string" "hash" {
  length  = 16
  special = false
}

resource "aws_s3_bucket" "redirect_bucket" {
  bucket = "redirect-${var.subdomain}${var.zone}-${lower(random_string.hash.result)}"
}

resource "aws_s3_bucket_website_configuration" "redirect_bucket" {
  bucket = aws_s3_bucket.redirect_bucket.bucket

  redirect_all_requests_to {
    host_name = var.target_url
    protocol  = "https"
  }
}

resource "aws_s3_bucket_public_access_block" "redirect_bucket" {
  bucket = aws_s3_bucket.redirect_bucket.id

  block_public_acls   = true
  block_public_policy = false
}

data "aws_iam_policy_document" "redirect_bucket_public_read" {
  statement {
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.redirect_bucket.arn}/*"]

    principals {
      type        = "AWS"
      identifiers = ["*"]
    }
  }

  statement {
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.redirect_bucket.arn]

    principals {
      type        = "AWS"
      identifiers = ["*"]
    }
  }
}

resource "aws_s3_bucket_policy" "redirect_bucket" {
  bucket = aws_s3_bucket.redirect_bucket.id
  policy = data.aws_iam_policy_document.redirect_bucket_public_read.json
}
