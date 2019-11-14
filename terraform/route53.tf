resource "aws_route53_zone" "ce-cdn-net" {
  name = "ce-cdn.net"
  tags = {
    Site = "CompilerExplorer"
  }
}

resource "aws_route53_record" "static-ce-cdn-net-A" {
  zone_id = "${aws_route53_zone.ce-cdn-net.zone_id}"
  name    = "static"
  type    = "A"

  alias {
    name                   = "${aws_cloudfront_distribution.static-ce-cdn-net.domain_name}"
    zone_id                = "${aws_cloudfront_distribution.static-ce-cdn-net.hosted_zone_id}"
    evaluate_target_health = false
  }
}

resource "aws_route53_record" "static-ce-cdn-net-AAAA" {
  zone_id = "${aws_route53_zone.ce-cdn-net.zone_id}"
  name    = "static"
  type    = "AAAA"

  alias {
    name                   = "${aws_cloudfront_distribution.static-ce-cdn-net.domain_name}"
    zone_id                = "${aws_cloudfront_distribution.static-ce-cdn-net.hosted_zone_id}"
    evaluate_target_health = false
  }
}

resource "aws_route53_record" "static-ce-cdn-net-acm" {
  zone_id = "${aws_route53_zone.ce-cdn-net.zone_id}"
  name    = "${aws_acm_certificate.static-ce-cdn-net.domain_validation_options.0.resource_record_name}"
  type    = "${aws_acm_certificate.static-ce-cdn-net.domain_validation_options.0.resource_record_type}"
  records = ["${aws_acm_certificate.static-ce-cdn-net.domain_validation_options.0.resource_record_value}"]
  ttl     = "60"
}
