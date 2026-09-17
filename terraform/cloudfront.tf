locals {
  deny_rate_limit_name_metric_name = "deny-rate-limit"
}
data "aws_acm_certificate" "godbolt-org-et-al" {
  domain      = "godbolt.org"
  types       = ["AMAZON_ISSUED"]
  most_recent = true
}

data "aws_acm_certificate" "static-ce-cdn-net" {
  domain      = "static.ce-cdn.net"
  most_recent = true
}

# Cache policy for the main app default behavior. Replaces the legacy
# forwarded_values block (which only supported gzip at the edge) so CloudFront
# can negotiate and serve brotli from the origin. The cache key and origin
# forward-set are kept identical to the previous forwarded_values: all query
# strings, the Accept/Host/CloudFront-Is-Mobile-Viewer headers, and no cookies.
resource "aws_cloudfront_cache_policy" "ce-app" {
  name        = "CompilerExplorerAppCachePolicy"
  comment     = "Default CE app behavior with brotli + gzip negotiation"
  min_ttl     = 0
  default_ttl = 86400
  max_ttl     = 31536000

  parameters_in_cache_key_and_forwarded_to_origin {
    enable_accept_encoding_brotli = true
    enable_accept_encoding_gzip   = true

    cookies_config {
      cookie_behavior = "none"
    }
    headers_config {
      header_behavior = "whitelist"
      headers {
        items = [
          "Accept",
          "Host",
          "CloudFront-Is-Mobile-Viewer"
        ]
      }
    }
    query_strings_config {
      query_string_behavior = "all"
    }
  }
}

resource "aws_cloudfront_distribution" "ce-godbolt-org" {
  comment = "CE on godbolt.org"
  origin {
    domain_name = "compiler-explorer.s3.amazonaws.com"
    origin_id   = "S3-compiler-explorer"
  }
  origin {
    domain_name = aws_alb.GccExplorerApp.dns_name
    origin_id   = "ALB-compiler-explorer"
    custom_origin_config {
      http_port                = 80
      https_port               = 443
      origin_read_timeout      = 60
      origin_keepalive_timeout = 60
      origin_protocol_policy   = "https-only"
      origin_ssl_protocols = [
        "TLSv1",
        "TLSv1.2",
        "TLSv1.1"
      ]
    }
  }

  enabled          = true
  is_ipv6_enabled  = true
  retain_on_delete = true
  aliases = [
    "godbolt.org",
    "*.godbolt.org"
  ]

  viewer_certificate {
    acm_certificate_arn      = data.aws_acm_certificate.godbolt-org-et-al.arn
    ssl_support_method       = "sni-only"
    minimum_protocol_version = "TLSv1.1_2016"
  }

  logging_config {
    include_cookies = false
    bucket          = "compiler-explorer-logs.s3.amazonaws.com"
    prefix          = "cloudfront/"
  }

  http_version = "http2"

  restrictions {
    geo_restriction {
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
    forwarded_values {
      cookies {
        forward = "none"
      }
      query_string = false
    }
    path_pattern           = "motd/*"
    target_origin_id       = "S3-compiler-explorer"
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
    forwarded_values {
      cookies {
        forward = "none"
      }
      query_string = false
    }
    path_pattern           = "admin/*"
    target_origin_id       = "S3-compiler-explorer"
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
    cache_policy_id        = aws_cloudfront_cache_policy.ce-app.id
    target_origin_id       = "ALB-compiler-explorer"
    viewer_protocol_policy = "redirect-to-https"
    compress               = true
  }

  custom_error_response {
    error_code            = 503
    response_code         = 503
    error_caching_min_ttl = 5
    response_page_path    = "/admin/503.html"
  }
  web_acl_id = aws_wafv2_web_acl.compiler-explorer.arn
}

# TODO - the duplication is rubbish
# Though note the differences: logging and aliases (at least).
resource "aws_cloudfront_distribution" "compiler-explorer-com" {
  comment = "CE on compiler-explorer.com"
  origin {
    domain_name = "compiler-explorer.s3.amazonaws.com"
    origin_id   = "S3-compiler-explorer"
  }
  origin {
    domain_name = aws_alb.GccExplorerApp.dns_name
    origin_id   = "ALB-compiler-explorer"
    custom_origin_config {
      http_port                = 80
      https_port               = 443
      origin_read_timeout      = 60
      origin_keepalive_timeout = 60
      origin_protocol_policy   = "https-only"
      origin_ssl_protocols = [
        "TLSv1",
        "TLSv1.2",
        "TLSv1.1"
      ]
    }
  }

  enabled          = true
  is_ipv6_enabled  = true
  retain_on_delete = true
  aliases = [
    "compiler-explorer.com",
    "*.compiler-explorer.com"
  ]

  viewer_certificate {
    acm_certificate_arn      = data.aws_acm_certificate.godbolt-org-et-al.arn
    ssl_support_method       = "sni-only"
    minimum_protocol_version = "TLSv1.1_2016"
  }

  logging_config {
    include_cookies = false
    bucket          = "compiler-explorer-logs.s3.amazonaws.com"
    prefix          = "cloudfront/"
  }

  http_version = "http2"

  restrictions {
    geo_restriction {
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
    forwarded_values {
      cookies {
        forward = "none"
      }
      query_string = false
    }
    path_pattern           = "motd/*"
    target_origin_id       = "S3-compiler-explorer"
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
    forwarded_values {
      cookies {
        forward = "none"
      }
      query_string = false
    }
    path_pattern           = "admin/*"
    target_origin_id       = "S3-compiler-explorer"
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
    cache_policy_id        = aws_cloudfront_cache_policy.ce-app.id
    target_origin_id       = "ALB-compiler-explorer"
    viewer_protocol_policy = "redirect-to-https"
    compress               = true
  }

  custom_error_response {
    error_code            = 503
    response_code         = 503
    error_caching_min_ttl = 5
    response_page_path    = "/admin/503.html"
  }
  web_acl_id = aws_wafv2_web_acl.compiler-explorer.arn
}

resource "aws_cloudfront_distribution" "godbo-lt" {
  comment = "CE on godbo.lt"
  origin {
    domain_name = "compiler-explorer.s3.amazonaws.com"
    origin_id   = "S3-compiler-explorer"
  }
  origin {
    domain_name = aws_alb.GccExplorerApp.dns_name
    origin_id   = "ALB-compiler-explorer"
    custom_origin_config {
      http_port                = 80
      https_port               = 443
      origin_read_timeout      = 60
      origin_keepalive_timeout = 60
      origin_protocol_policy   = "https-only"
      origin_ssl_protocols = [
        "TLSv1",
        "TLSv1.2",
        "TLSv1.1"
      ]
    }
  }

  enabled          = true
  is_ipv6_enabled  = true
  retain_on_delete = true
  aliases = [
    "godbo.lt",
    "*.godbo.lt"
  ]

  viewer_certificate {
    acm_certificate_arn      = data.aws_acm_certificate.godbolt-org-et-al.arn
    ssl_support_method       = "sni-only"
    minimum_protocol_version = "TLSv1.1_2016"
  }

  logging_config {
    include_cookies = false
    bucket          = "compiler-explorer-logs.s3.amazonaws.com"
    prefix          = "cloudfront/"
  }

  http_version = "http2"

  restrictions {
    geo_restriction {
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
    forwarded_values {
      cookies {
        forward = "none"
      }
      query_string = false
    }
    path_pattern           = "motd/*"
    target_origin_id       = "S3-compiler-explorer"
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
    forwarded_values {
      cookies {
        forward = "none"
      }
      query_string = false
    }
    path_pattern           = "admin/*"
    target_origin_id       = "S3-compiler-explorer"
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
    cache_policy_id        = aws_cloudfront_cache_policy.ce-app.id
    target_origin_id       = "ALB-compiler-explorer"
    viewer_protocol_policy = "redirect-to-https"
    compress               = true
  }

  custom_error_response {
    error_code            = 503
    response_code         = 503
    error_caching_min_ttl = 5
    response_page_path    = "/admin/503.html"
  }

  web_acl_id = aws_wafv2_web_acl.compiler-explorer.arn
}

resource "aws_cloudfront_distribution" "static-ce-cdn-net" {
  comment = "CE CDN"
  origin {
    domain_name = "ce-cdn.net.s3.amazonaws.com"
    origin_id   = "S3-ce-cdn.net"
  }

  enabled          = true
  is_ipv6_enabled  = true
  retain_on_delete = true
  aliases = [
    "static.ce-cdn.net"
  ]

  viewer_certificate {
    acm_certificate_arn      = data.aws_acm_certificate.static-ce-cdn-net.arn
    ssl_support_method       = "sni-only"
    minimum_protocol_version = "TLSv1.1_2016"
  }

  logging_config {
    include_cookies = false
    bucket          = "compiler-explorer-logs.s3.amazonaws.com"
    prefix          = "cloudfront/"
  }

  http_version = "http2"

  restrictions {
    geo_restriction {
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

  default_cache_behavior {
    allowed_methods = [
      "HEAD",
      "GET",
      "OPTIONS"
    ]
    cached_methods = [
      "HEAD",
      "GET",
      "OPTIONS"
    ]
    forwarded_values {
      cookies {
        forward = "none"
      }
      headers = [
        # see https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/header-caching.html#header-caching-web-cors
        "Origin",
        "Access-Control-Request-Headers",
        "Access-Control-Request-Method"
      ]
      query_string = true
      query_string_cache_keys = [
        "v"
      ]
    }
    target_origin_id       = "S3-ce-cdn.net"
    viewer_protocol_policy = "redirect-to-https"
    compress               = true
  }
}

resource "aws_wafv2_web_acl" "compiler-explorer" {
  name  = "CompilerExplorer"
  scope = "CLOUDFRONT"
  default_action {
    allow {}
  }

  rule {
    name     = "deny-ipv4"
    priority = 0
    action {
      block {}
    }
    statement {
      ip_set_reference_statement {
        arn = aws_wafv2_ip_set.banned-ipv4.arn
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "deny-ipv4"
      sampled_requests_enabled   = true
    }
  }

  rule {
    name     = "deny-ipv6"
    priority = 1
    action {
      block {}
    }
    statement {
      ip_set_reference_statement {
        arn = aws_wafv2_ip_set.banned-ipv6.arn
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "deny-ipv6"
      sampled_requests_enabled   = true
    }
  }

  rule {
    name     = "RateLimitPost"
    priority = 2
    action {
      block {
        custom_response {
          response_code            = 429
          custom_response_body_key = "blocked-ratelimit"
          response_header {
            name  = "Retry-After"
            value = "300"
          }
        }
      }
    }
    statement {
      rate_based_statement {
        // Limit to this many per 5 minutes (300 seconds)
        limit              = 12000
        aggregate_key_type = "IP"
        scope_down_statement {
          byte_match_statement {
            positional_constraint = "EXACTLY"
            search_string         = "POST"
            field_to_match {
              method {}
            }
            text_transformation {
              priority = 0
              type     = "NONE"
            }
          }
        }
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = local.deny_rate_limit_name_metric_name
      sampled_requests_enabled   = true
    }
  }

  # Scanners hit *.godbolt.org with multi-label hosts (dev.app.godbolt.org etc); CloudFront
  # then fails origin TLS against the ALB's *.godbolt.org cert and synthesises 502s that trip
  # High5xx (infra#2310). Costs $1/month; consider removing if the scanner traffic goes away.
  rule {
    name     = "deny-bogus-host"
    priority = 3
    action {
      block {}
    }
    statement {
      not_statement {
        statement {
          regex_match_statement {
            regex_string = "^([a-z0-9_-]+\\.)?(godbolt\\.org|compiler-explorer\\.com|godbo\\.lt)(:[0-9]+)?$"
            field_to_match {
              single_header {
                name = "host"
              }
            }
            text_transformation {
              priority = 0
              type     = "LOWERCASE"
            }
          }
        }
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "deny-bogus-host"
      sampled_requests_enabled   = true
    }
  }

  # No real client arrives via its own loopback; only scanners forge X-Forwarded-For: 127.0.0.1.
  rule {
    name     = "deny-loopback-forwarded-for"
    priority = 4
    action {
      block {}
    }
    statement {
      regex_match_statement {
        regex_string = "(^|[, ])(127\\.[0-9]+\\.[0-9]+\\.[0-9]+|::ffff:127\\.[0-9]+\\.[0-9]+\\.[0-9]+|::1|localhost)($|[, ])"
        field_to_match {
          single_header {
            name = "x-forwarded-for"
          }
        }
        text_transformation {
          priority = 0
          type     = "LOWERCASE"
        }
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "deny-loopback-forwarded-for"
      sampled_requests_enabled   = true
    }
  }

  # AWS-maintained bot classification, in count mode: per-rule metrics and labels only. To block, set
  # override_action to none and keep any rule you still only want counted with rule_action_override.
  rule {
    name     = "bot-control-observe"
    priority = 10
    override_action {
      count {}
    }
    statement {
      managed_rule_group_statement {
        vendor_name = "AWS"
        name        = "AWSManagedRulesBotControlRuleSet"
        managed_rule_group_configs {
          aws_managed_rules_bot_control_rule_set {
            inspection_level = "COMMON"
          }
        }
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "bot-control-observe"
      sampled_requests_enabled   = true
    }
  }

  # Keyed by TLS fingerprint, not IP: scanner farms rotate addresses faster than a rate rule reacts
  # but keep one fingerprint. Verified crawlers never carry the label; HTTP libraries (curl, Ruby,
  # python-requests...) are excluded so API scripts are never throttled here.
  rule {
    name     = "rate-limit-non-browser"
    priority = 11
    action {
      block {
        custom_response {
          response_code            = 429
          custom_response_body_key = "blocked-ratelimit"
          response_header {
            name  = "Retry-After"
            value = "60"
          }
        }
      }
    }
    statement {
      rate_based_statement {
        limit                 = 100
        evaluation_window_sec = 60
        aggregate_key_type    = "CUSTOM_KEYS"
        custom_key {
          ja4_fingerprint {
            fallback_behavior = "NO_MATCH"
          }
        }
        scope_down_statement {
          and_statement {
            statement {
              label_match_statement {
                scope = "LABEL"
                key   = "awswaf:managed:aws:bot-control:signal:non_browser_user_agent"
              }
            }
            statement {
              not_statement {
                statement {
                  label_match_statement {
                    scope = "LABEL"
                    key   = "awswaf:managed:aws:bot-control:bot:category:http_library"
                  }
                }
              }
            }
          }
        }
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "rate-limit-non-browser"
      sampled_requests_enabled   = true
    }
  }

  custom_response_body {
    content      = "Your request has hit our rate limit. Please reduce the load you're putting on our site. Contact us on Discord if you feel this is in error."
    content_type = "TEXT_PLAIN"
    key          = "blocked-ratelimit"
  }

  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "ok"
    sampled_requests_enabled   = true
  }
}

resource "aws_wafv2_ip_set" "banned-ipv4" {
  name               = "banned-ipv4"
  description        = "Banned ipv4"
  scope              = "CLOUDFRONT"
  ip_address_version = "IPV4"
  addresses          = []
}

resource "aws_wafv2_ip_set" "banned-ipv6" {
  name               = "banned-ipv6"
  description        = "Banned ipv6"
  scope              = "CLOUDFRONT"
  ip_address_version = "IPV6"
  addresses = [
    "2001:b011:d006:13f8:0000:0000:0000:0000/64" // Anomolous behaviour; large number of requests on 2025/01/05
  ]
}
