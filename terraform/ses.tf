resource "aws_ses_domain_identity" "compiler-explorer-com" {
  domain = aws_route53_zone.compiler-explorer-com.name
}
