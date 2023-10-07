resource "aws_cloudfront_distribution" "lambdas-compiler-explorer-com" {
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
    allowed_methods = [
      "HEAD",
      "GET"
    ]
    cached_methods = [
      "HEAD",
      "GET"
    ]
    forwarded_values {
      cookies {
        forward = "none"
      }
      query_string = true
      headers      = [
        "Accept",
        "Host"
      ]
    }
    target_origin_id       = aws_apigatewayv2_api.ce_pub_lambdas.id
    viewer_protocol_policy = "redirect-to-https"
    compress               = true
    max_ttl                = 3600
  }
}
