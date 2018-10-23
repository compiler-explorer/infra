resource "aws_cloudfront_distribution" "ce-godbolt-org" {
  origin {
    domain_name = "compiler-explorer.s3.amazonaws.com"
    origin_id = "S3-compiler-explorer"
  }
  origin {
    domain_name = "GccExplorerApp-2127314270.us-east-1.elb.amazonaws.com"
    origin_id = "ELB-GccExplorerApp-2127314270"
    custom_origin_config {
      http_port = 80
      https_port = 443
      origin_protocol_policy = "https-only"
      origin_ssl_protocols = [
        "TLSv1",
        "TLSv1.2",
        "TLSv1.1"
      ]
    }
  }

  enabled = true
  is_ipv6_enabled = true
  retain_on_delete = true
  aliases = [
    "godbolt.org",
    "*.godbolt.org"
  ]

  viewer_certificate {
    acm_certificate_arn = "arn:aws:acm:us-east-1:052730242331:certificate/9b8deb50-0841-4715-9e12-d7db6551325e"
    ssl_support_method = "sni-only"
    minimum_protocol_version = "TLSv1.1_2016"
  }

  logging_config {
    include_cookies = false
    bucket = "compiler-explorer.s3.amazonaws.com"
    prefix = "cloudfront-logs/"
  }

  http_version = "http2"

  restrictions {
    "geo_restriction" {
      restriction_type = "blacklist"
      locations = [
        "CU",
        "IR",
        "KP",
        "SD",
        "SY"
      ]
    }
  }

  # Message of the day stuff, served from s3
  ordered_cache_behavior {
    allowed_methods = [
      "GET",
      "HEAD"
    ]
    cached_methods = [
      "GET",
      "HEAD"
    ]
    "forwarded_values" {
      "cookies" {
        forward = "none"
      }
      query_string = false
    }
    path_pattern = "motd/*"
    target_origin_id = "S3-compiler-explorer"
    viewer_protocol_policy = "redirect-to-https"
  }

  # Admin stuff, also served from s3
  ordered_cache_behavior {
    allowed_methods = [
      "GET",
      "HEAD"
    ]
    cached_methods = [
      "GET",
      "HEAD"
    ]
    "forwarded_values" {
      "cookies" {
        forward = "none"
      }
      query_string = false
    }
    path_pattern = "admin/*"
    target_origin_id = "S3-compiler-explorer"
    viewer_protocol_policy = "redirect-to-https"
  }

  default_cache_behavior {
    allowed_methods = [
      "HEAD",
      "DELETE",
      "POST",
      "GET",
      "OPTIONS",
      "PUT",
      "PATCH"
    ]
    cached_methods = [
      "HEAD",
      "GET"
    ]
    "forwarded_values" {
      "cookies" {
        forward = "none"
      }
      query_string = false
      headers = [
        "Accept",
        "Host"
      ]
    }
    target_origin_id = "ELB-GccExplorerApp-2127314270"
    viewer_protocol_policy = "redirect-to-https"
    compress = true
  }

  tags {
    Site = "CompilerExplorer"
  }
}

# TODO - the duplication is rubbish
# Though note the differences: viewer certificate, logging, origin protocol policy and aliases (at least).
resource "aws_cloudfront_distribution" "compiler-explorer-com" {
  origin {
    domain_name = "compiler-explorer.s3.amazonaws.com"
    origin_id = "S3-compiler-explorer"
  }
  origin {
    domain_name = "GccExplorerApp-2127314270.us-east-1.elb.amazonaws.com"
    origin_id = "ELB-GccExplorerApp-2127314270"
    custom_origin_config {
      http_port = 80
      https_port = 443
      # Certificate on the endpoint is godbolt.org
      origin_protocol_policy = "http-only"
      origin_ssl_protocols = [
        "TLSv1",
        "TLSv1.2",
        "TLSv1.1"
      ]
    }
  }

  enabled = true
  is_ipv6_enabled = true
  retain_on_delete = true
  aliases = [
    "compiler-explorer.com",
    "*.compiler-explorer.com"
  ]

  viewer_certificate {
    acm_certificate_arn = "arn:aws:acm:us-east-1:052730242331:certificate/7abed4ab-ecfc-4020-8f73-f255fd82f079"
    ssl_support_method = "sni-only"
    minimum_protocol_version = "TLSv1.1_2016"
  }

  logging_config {
    include_cookies = false
    bucket = "compiler-explorer.s3.amazonaws.com"
    prefix = "cloudfront-logs-ce/"
  }

  http_version = "http2"

  restrictions {
    "geo_restriction" {
      restriction_type = "blacklist"
      locations = [
        "CU",
        "IR",
        "KP",
        "SD",
        "SY"
      ]
    }
  }

  # Message of the day stuff, served from s3
  ordered_cache_behavior {
    allowed_methods = [
      "GET",
      "HEAD"
    ]
    cached_methods = [
      "GET",
      "HEAD"
    ]
    "forwarded_values" {
      "cookies" {
        forward = "none"
      }
      query_string = false
    }
    path_pattern = "motd/*"
    target_origin_id = "S3-compiler-explorer"
    viewer_protocol_policy = "redirect-to-https"
  }

  # Admin stuff, also served from s3
  ordered_cache_behavior {
    allowed_methods = [
      "GET",
      "HEAD"
    ]
    cached_methods = [
      "GET",
      "HEAD"
    ]
    "forwarded_values" {
      "cookies" {
        forward = "none"
      }
      query_string = false
    }
    path_pattern = "admin/*"
    target_origin_id = "S3-compiler-explorer"
    viewer_protocol_policy = "redirect-to-https"
  }

  default_cache_behavior {
    allowed_methods = [
      "HEAD",
      "DELETE",
      "POST",
      "GET",
      "OPTIONS",
      "PUT",
      "PATCH"
    ]
    cached_methods = [
      "HEAD",
      "GET"
    ]
    "forwarded_values" {
      "cookies" {
        forward = "none"
      }
      query_string = false
      headers = [
        "Accept",
        "Host"
      ]
    }
    target_origin_id = "ELB-GccExplorerApp-2127314270"
    viewer_protocol_policy = "redirect-to-https"
    compress = true
  }

  tags {
    Site = "CompilerExplorer"
  }
}
