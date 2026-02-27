resource "aws_cloudfront_distribution" "redirect" {
  origin {
    domain_name = "${aws_s3_bucket.redirect_bucket.bucket}.s3-website.${data.aws_region.current.id}.amazonaws.com"
    origin_id   = aws_s3_bucket.redirect_bucket.bucket

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "http-only"
      origin_ssl_protocols   = ["SSLv3", "TLSv1", "TLSv1.1", "TLSv1.2"]
    }
  }

  price_class     = "PriceClass_100"
  comment         = aws_s3_bucket.redirect_bucket.bucket
  enabled         = true
  is_ipv6_enabled = false

  aliases = ["www.${var.subdomain}${var.zone}", "${var.subdomain}${var.zone}"]

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  default_cache_behavior {
    allowed_methods  = ["GET", "HEAD"]
    cached_methods   = ["GET", "HEAD"]
    target_origin_id = aws_s3_bucket.redirect_bucket.bucket
    compress         = true

    min_ttl     = 31536000
    max_ttl     = 31536000
    default_ttl = 31536000

    forwarded_values {
      query_string = var.cloudfront_forward_query_string

      cookies {
        forward = "none"
      }
    }

    viewer_protocol_policy = "allow-all"
  }

  viewer_certificate {
    acm_certificate_arn = aws_acm_certificate.cert.arn
    ssl_support_method  = "sni-only"
  }

  wait_for_deployment = var.cloudfront_wait_for_deployment
}
