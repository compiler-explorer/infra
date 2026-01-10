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

// Bluesky for the Matt
resource "aws_route53_record" "atproto-matt-godbolt-org" {
  name    = "_atproto.matt"
  zone_id = module.godbolt-org.zone_id
  ttl     = 3600
  type    = "TXT"
  records = ["did=did:plc:vbbhrlxqrokfgnvuppfyeir5"]
}

// Test for auth - dev only do not use
resource "aws_route53_record" "auth-godbolt-org" {
  name    = "auth"
  zone_id = module.godbolt-org.zone_id
  ttl     = 3600
  type    = "CNAME"
  records = ["dev-ce-vupzkjx14g5sjvco-cd-qtr5mjlqgunghpuo.edge.tenants.us.auth0.com"]
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

// Bluesky for the CE account
resource "aws_route53_record" "atproto-compiler-explorer-com" {
  name    = "_atproto"
  zone_id = module.compiler-explorer-com.zone_id
  ttl     = 3600
  type    = "TXT"
  records = ["did=did:plc:pz3zlp6rmegaiifji2scmyi2"]
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

resource "aws_ses_domain_mail_from" "compiler-explorer-com" {
  domain                 = aws_ses_domain_identity.compiler-explorer-com.domain
  mail_from_domain       = "bounce.${aws_ses_domain_identity.compiler-explorer-com.domain}"
  behavior_on_mx_failure = "UseDefaultValue"
}

resource "aws_route53_record" "ses-bounce-mx-compiler-explorer-com" {
  name    = aws_ses_domain_mail_from.compiler-explorer-com.mail_from_domain
  zone_id = module.compiler-explorer-com.zone_id
  ttl     = 3600
  type    = "MX"
  records = ["10 feedback-smtp.us-east-1.amazonses.com"]
}

resource "aws_route53_record" "ses-bounce-spf-compiler-explorer-com" {
  name    = aws_ses_domain_mail_from.compiler-explorer-com.mail_from_domain
  zone_id = module.compiler-explorer-com.zone_id
  ttl     = 3600
  type    = "TXT"
  records = ["v=spf1 include:amazonses.com ~all"]
}

resource "aws_ses_domain_dkim" "compiler-explorer-com" {
  domain = aws_ses_domain_identity.compiler-explorer-com.domain
}

resource "aws_route53_record" "ses-dkim-compiler-explorer-com" {
  count   = 3
  name    = "${aws_ses_domain_dkim.compiler-explorer-com.dkim_tokens[count.index]}._domainkey"
  zone_id = module.compiler-explorer-com.zone_id
  ttl     = 3600
  type    = "CNAME"
  records = ["${aws_ses_domain_dkim.compiler-explorer-com.dkim_tokens[count.index]}.dkim.amazonses.com"]
}

resource "aws_route53_record" "dmarc-compiler-explorer-com" {
  name    = "_dmarc"
  zone_id = module.compiler-explorer-com.zone_id
  ttl     = 3600
  type    = "TXT"
  records = ["v=DMARC1; p=quarantine; rua=mailto:matt+dmarc@compiler-explorer.com"]
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

resource "aws_route53_record" "events-compiler-explorer-com" {
  name    = aws_apigatewayv2_domain_name.events-api-compiler-explorer-custom-domain.domain_name
  type    = "A"
  zone_id = module.compiler-explorer-com.zone_id

  alias {
    name                   = aws_apigatewayv2_domain_name.events-api-compiler-explorer-custom-domain.domain_name_configuration[0].target_domain_name
    zone_id                = aws_apigatewayv2_domain_name.events-api-compiler-explorer-custom-domain.domain_name_configuration[0].hosted_zone_id
    evaluate_target_health = false
  }
}

// Shop DNS records for fourthwall.com integration
resource "aws_route53_record" "shop-compiler-explorer-com" {
  name    = "shop"
  zone_id = module.compiler-explorer-com.zone_id
  ttl     = 3600
  type    = "A"
  records = ["34.117.223.165"]
}

resource "aws_route53_record" "www-shop-compiler-explorer-com" {
  name    = "www.shop"
  zone_id = module.compiler-explorer-com.zone_id
  ttl     = 3600
  type    = "CNAME"
  records = ["shop.compiler-explorer.com."]
}

// SendGrid CNAME records for support.shop
resource "aws_route53_record" "em-fw-support-shop-compiler-explorer-com" {
  name    = "em-fw.support.shop"
  zone_id = module.compiler-explorer-com.zone_id
  ttl     = 3600
  type    = "CNAME"
  records = ["u45139959.wl210.sendgrid.net."]
}

resource "aws_route53_record" "s1-domainkey-support-shop-compiler-explorer-com" {
  name    = "s1._domainkey.support.shop"
  zone_id = module.compiler-explorer-com.zone_id
  ttl     = 3600
  type    = "CNAME"
  records = ["s1.domainkey.u45139959.wl210.sendgrid.net."]
}

resource "aws_route53_record" "s2-domainkey-support-shop-compiler-explorer-com" {
  name    = "s2._domainkey.support.shop"
  zone_id = module.compiler-explorer-com.zone_id
  ttl     = 3600
  type    = "CNAME"
  records = ["s2.domainkey.u45139959.wl210.sendgrid.net."]
}

// Zendesk CNAME records for support.shop
resource "aws_route53_record" "zendesk1-domainkey-support-shop-compiler-explorer-com" {
  name    = "zendesk1._domainkey.support.shop"
  zone_id = module.compiler-explorer-com.zone_id
  ttl     = 3600
  type    = "CNAME"
  records = ["zendesk1._domainkey.zendesk.com."]
}

resource "aws_route53_record" "zendesk2-domainkey-support-shop-compiler-explorer-com" {
  name    = "zendesk2._domainkey.support.shop"
  zone_id = module.compiler-explorer-com.zone_id
  ttl     = 3600
  type    = "CNAME"
  records = ["zendesk2._domainkey.zendesk.com."]
}

resource "aws_route53_record" "zendesk1-support-shop-compiler-explorer-com" {
  name    = "zendesk1.support.shop"
  zone_id = module.compiler-explorer-com.zone_id
  ttl     = 3600
  type    = "CNAME"
  records = ["mail1.zendesk.com."]
}

resource "aws_route53_record" "zendesk2-support-shop-compiler-explorer-com" {
  name    = "zendesk2.support.shop"
  zone_id = module.compiler-explorer-com.zone_id
  ttl     = 3600
  type    = "CNAME"
  records = ["mail2.zendesk.com."]
}

resource "aws_route53_record" "zendesk3-support-shop-compiler-explorer-com" {
  name    = "zendesk3.support.shop"
  zone_id = module.compiler-explorer-com.zone_id
  ttl     = 3600
  type    = "CNAME"
  records = ["mail3.zendesk.com."]
}

resource "aws_route53_record" "zendesk4-support-shop-compiler-explorer-com" {
  name    = "zendesk4.support.shop"
  zone_id = module.compiler-explorer-com.zone_id
  ttl     = 3600
  type    = "CNAME"
  records = ["mail4.zendesk.com."]
}

// TXT records for support.shop email verification and policies
resource "aws_route53_record" "zendeskverification-support-shop-compiler-explorer-com" {
  name    = "zendeskverification.support.shop"
  zone_id = module.compiler-explorer-com.zone_id
  ttl     = 3600
  type    = "TXT"
  records = ["7e2a8a956b617a3b"]
}

resource "aws_route53_record" "dmarc-support-shop-compiler-explorer-com" {
  name    = "_dmarc.support.shop"
  zone_id = module.compiler-explorer-com.zone_id
  ttl     = 3600
  type    = "TXT"
  records = ["v=DMARC1; p=reject; pct=100; rua=mailto:dmarc@fourthwall.com"]
}

resource "aws_route53_record" "spf-support-shop-compiler-explorer-com" {
  name    = "support.shop"
  zone_id = module.compiler-explorer-com.zone_id
  ttl     = 3600
  type    = "TXT"
  records = ["v=spf1 include:_spf.google.com include:mail.zendesk.com include:spf.improvmx.com include:sendgrid.net ~all"]
}

// MX records for support.shop email handling via ImprovMX
resource "aws_route53_record" "mx-support-shop-compiler-explorer-com" {
  name    = "support.shop"
  zone_id = module.compiler-explorer-com.zone_id
  ttl     = 3600
  type    = "MX"
  records = [
    "10 mx1.improvmx.com.",
    "20 mx2.improvmx.com."
  ]
}


////////////////////////////////////////////////////

module "godbo-lt" {
  source                  = "./modules/ce_dns"
  domain_name             = "godbo.lt"
  cloudfront_distribution = aws_cloudfront_distribution.godbo-lt
  certificate             = aws_acm_certificate.godbolt-org-et-al
}


////////////////////////////////////////////////////

# Route 53 hosted zone for godbolt.net (not active yet, just transferred)
resource "aws_route53_zone" "godbolt-net" {
  name    = "godbolt.net"
  comment = "godbolt.net domain"
}

resource "aws_route53domains_registered_domain" "godbolt-net" {
  domain_name = "godbolt.net"

  dynamic "name_server" {
    for_each = toset(aws_route53_zone.godbolt-net.name_servers)
    content {
      name = name_server.value
    }
  }
}
