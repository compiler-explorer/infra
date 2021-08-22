resource "aws_route53_zone" "ce-cdn-net" {
  name = "ce-cdn.net"
}

resource "aws_route53_record" "static-ce-cdn-net-A" {
  zone_id = aws_route53_zone.ce-cdn-net.zone_id
  name    = "static"
  type    = "A"

  alias {
    name                   = aws_cloudfront_distribution.static-ce-cdn-net.domain_name
    zone_id                = aws_cloudfront_distribution.static-ce-cdn-net.hosted_zone_id
    evaluate_target_health = false
  }
}

resource "aws_route53_record" "static-ce-cdn-net-AAAA" {
  zone_id = aws_route53_zone.ce-cdn-net.zone_id
  name    = "static"
  type    = "AAAA"

  alias {
    name                   = aws_cloudfront_distribution.static-ce-cdn-net.domain_name
    zone_id                = aws_cloudfront_distribution.static-ce-cdn-net.hosted_zone_id
    evaluate_target_health = false
  }
}

resource "aws_route53_record" "static-ce-cdn-net-acm" {
  for_each = {
  for dvo in aws_acm_certificate.static-ce-cdn-net.domain_validation_options : dvo.domain_name => {
    name   = dvo.resource_record_name
    record = dvo.resource_record_value
    type   = dvo.resource_record_type
  }
  }

  zone_id = aws_route53_zone.ce-cdn-net.zone_id
  name    = each.value.name
  type    = each.value.type
  records = [each.value.record]
  ttl     = 60
}

module godbo-lt {
  source = "./modules/ce_dns"
  domain_name = "godbo.lt"
  cloudfront_distribution = aws_cloudfront_distribution.godbo-lt
  certificate = aws_acm_certificate.godbolt-org-et-al
}

module compiler-explorer-com {
  source = "./modules/ce_dns"
  domain_name = "compiler-explorer.com"
  cloudfront_distribution = aws_cloudfront_distribution.compiler-explorer-com
  certificate = aws_acm_certificate.godbolt-org-et-al
}

resource "aws_route53_record" "gh-compiler-explorer-com" {
  name    = "_github-challenge-compiler-explorer"
  zone_id = module.compiler-explorer-com.zone_id
  ttl     = 3600
  type    = "TXT"
  records = ["a5417612c3"]
}

resource "aws_ses_domain_identity" "compiler-explorer-com" {
  domain = "compiler-explorer.com"
}

resource "aws_route53_record" "ses-compiler-explorer-com" {
  name    = "_amazonses"
  zone_id = module.compiler-explorer-com.zone_id
  ttl     = 3600
  type    = "TXT"
  records = [aws_ses_domain_identity.compiler-explorer-com.verification_token]
}
