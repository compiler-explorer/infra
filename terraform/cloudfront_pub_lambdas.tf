resource "aws_cloudfront_distribution" "lambdas-compiler-explorer-com" {
  origin {
    domain_name = "compiler-explorer.s3.amazonaws.com"
    origin_id   = "S3-compiler-explorer"
  }
  origin {
    domain_name = "${aws_apigatewayv2_api.ce_pub_lambdas.id}.execute-api.us-east-1.amazonaws.com"
    origin_id   = aws_apigatewayv2_api.ce_pub_lambdas.id
    custom_origin_config {
      http_port              = "80"
      https_port             = "443"
      origin_protocol_policy = "https-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  enabled          = true
  is_ipv6_enabled  = true
  retain_on_delete = false
  aliases          = [
    "lambdas.compiler-explorer.com"
  ]

  viewer_certificate {
    acm_certificate_arn      = data.aws_acm_certificate.godbolt-org-et-al.arn
    ssl_support_method       = "sni-only"
    minimum_protocol_version = "TLSv1.2_2021"
  }

  logging_config {
    include_cookies = false
    bucket          = "compiler-explorer-logs.s3.amazonaws.com"
    prefix          = "cloudfront/"
  }

  http_version = "http2"

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  default_cache_behavior {
    allowed_methods  = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
    cached_methods   = ["GET", "HEAD"]
    target_origin_id = "S3-compiler-explorer"

    forwarded_values {
      query_string = false

      cookies {
        forward = "none"
      }
    }

    viewer_protocol_policy = "allow-all"
    min_ttl                = 0
    default_ttl            = 3600
    max_ttl                = 86400
  }

  ordered_cache_behavior {
    path_pattern     = "/prod/*"
    allowed_methods  = ["GET", "HEAD", "OPTIONS"]
    cached_methods   = ["GET", "HEAD"]
    target_origin_id = aws_apigatewayv2_api.ce_pub_lambdas.id
    cache_policy_id  = "4135ea2d-6df8-44a3-9df3-4b5a84be39ad" # CachingDisabled
    origin_request_policy_id = "b689b0a8-53d0-40ab-baf2-68738e2966ac" # AllViewerExceptHostHeader
    response_headers_policy_id = "60669652-455b-4ae9-85a4-c4c02393f86c" # SimpleCORS

    min_ttl                = 60
    default_ttl            = 1800
    max_ttl                = 3600
    compress               = true
    viewer_protocol_policy = "https-only"
  }
}
