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
  ttl     = "60"
}

resource "aws_route53_zone" "godbo-lt" {
  name = "godbo.lt"
}

resource "aws_route53_record" "godbo-lt" {
  for_each = {
    a    = "A"
    aaaa = "AAAA"
  }
  zone_id  = aws_route53_zone.godbo-lt.zone_id
  name     = ""
  type     = each.value
  alias {
    name                   = aws_cloudfront_distribution.godbo-lt.domain_name
    zone_id                = aws_cloudfront_distribution.godbo-lt.hosted_zone_id
    evaluate_target_health = false
  }
}

resource "aws_route53_record" "star-godbo-lt" {
  zone_id = aws_route53_zone.godbo-lt.zone_id
  name    = "*"
  type    = "CNAME"
  ttl     = "60"
  records = [aws_route53_zone.godbo-lt.name]
}

resource "aws_route53_record" "spf-godbo-lt" {
  zone_id = aws_route53_zone.godbo-lt.zone_id
  name    = ""
  type    = "SPF"
  ttl     = "3600"
  records = ["v=spf1 a include:_spf.google.com ~all"]
}

resource "aws_route53_record" "mail-godbo-lt" {
  name    = ""
  type    = "MX"
  ttl     = "3600"
  zone_id = aws_route53_zone.godbo-lt.zone_id
  records = [
    "1 aspmx.l.google.com",
    "5 alt1.aspmx.l.google.com",
    "5 alt2.aspmx.l.google.com",
    "10 alt3.aspmx.l.google.com",
    "10 alt4.aspmx.l.google.com",
  ]
}

resource "aws_route53_record" "godbo-lt-acm" {
  for_each = {
  for dvo in aws_acm_certificate.godbolt-org-et-al.domain_validation_options : dvo.domain_name => {
    name   = dvo.resource_record_name
    record = dvo.resource_record_value
    type   = dvo.resource_record_type
  }
  }

  allow_overwrite = true
  name            = each.value.name
  zone_id         = aws_route53_zone.godbo-lt.zone_id
  type            = each.value.type
  records         = [each.value.record]
  ttl             = "60"
}
