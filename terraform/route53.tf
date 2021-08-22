module ce-cdn-net {
  source = "./modules/ce_dns"
  domain_name = "ce-cdn.net"
  top_level_name = "static"
  cloudfront_distribution = aws_cloudfront_distribution.static-ce-cdn-net
  certificate = aws_acm_certificate.static-ce-cdn-net
  wildcard = false
  mail = false
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
