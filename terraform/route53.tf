module "ce-cdn-net" {
  source                  = "./modules/ce_dns"
  domain_name             = "ce-cdn.net"
  top_level_name          = "static"
  cloudfront_distribution = aws_cloudfront_distribution.static-ce-cdn-net
  certificate             = aws_acm_certificate.static-ce-cdn-net
  wildcard                = false
  mail                    = false
}

////////////////////////////////////////////////////

module "godbolt-org" {
  source                  = "./modules/ce_dns"
  domain_name             = "godbolt.org"
  cloudfront_distribution = aws_cloudfront_distribution.ce-godbolt-org
  certificate             = aws_acm_certificate.godbolt-org-et-al
}

resource "aws_route53_record" "google-hosted-stuff-godbolt-org" {
  for_each = {
    mail     = "mail"
    url      = "url"
    calendar = "calendar"
  }
  name    = each.value
  zone_id = module.godbolt-org.zone_id
  ttl     = 3600
  type    = "CNAME"
  records = ["ghs.googlehosted.com"]
}

// Concessions for Matt's old non-Compiler Explorer websites.
module "route53-domain-redirect" {
  for_each = {
    bbc     = "bbc"
    master  = "master"
    beebide = "beebide"
  }
  source                          = "trebidav/route53-domain-redirect/module"
  version                         = "0.4.0"
  zone                            = "godbolt.org"
  subdomain                       = format("%s.", each.value)
  target_url                      = format("%s.xania.org", each.value)
  cloudfront_forward_query_string = true
}

resource "aws_route53_record" "gh-godbolt-org" {
  name    = "_github-challenge-compiler-explorer"
  zone_id = module.godbolt-org.zone_id
  ttl     = 3600
  type    = "TXT"
  records = ["78a5d77c2a"]
}


resource "aws_route53_record" "dkim-godbolt-org" {
  name    = "google._domainkey"
  zone_id = module.godbolt-org.zone_id
  ttl     = 3600
  type    = "TXT"
  records = [
    "v=DKIM1; k=rsa; p=MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQCYl6muZHDYPuwza5M/Ba4coCeQShiWZ7qIaZgiWWhicS/0Xtesz88hFRdQHs6KlxiKUsPw8053SpS9NVLoq3jWeWce4JJgBNXi29WEnID0SJSdyq9xgpe1GThZccem21rHOk0t1VdQDoXUvhDTI3HaGmODMv7FNQm2nz1yNZDP1QIDAQAB"
  ]
}


////////////////////////////////////////////////////

module "compiler-explorer-com" {
  source                  = "./modules/ce_dns"
  domain_name             = "compiler-explorer.com"
  cloudfront_distribution = aws_cloudfront_distribution.compiler-explorer-com
  certificate             = aws_acm_certificate.godbolt-org-et-al
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

resource "aws_route53_record" "api-compiler-explorer-com" {
  name    = aws_apigatewayv2_domain_name.api-compiler-explorer-custom-domain.domain_name
  type    = "A"
  zone_id = module.compiler-explorer-com.zone_id

  alias {
    name                   = aws_apigatewayv2_domain_name.api-compiler-explorer-custom-domain.domain_name_configuration[0].target_domain_name
    zone_id                = aws_apigatewayv2_domain_name.api-compiler-explorer-custom-domain.domain_name_configuration[0].hosted_zone_id
    evaluate_target_health = false
  }
}

////////////////////////////////////////////////////

module "godbo-lt" {
  source                  = "./modules/ce_dns"
  domain_name             = "godbo.lt"
  cloudfront_distribution = aws_cloudfront_distribution.godbo-lt
  certificate             = aws_acm_certificate.godbolt-org-et-al
}
