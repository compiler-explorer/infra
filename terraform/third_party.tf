module "oidc_provider" {
  source = "github.com/philips-labs/terraform-aws-github-oidc?ref=v0.6.0//modules/provider"
}

module "oidc_repo_sonar_source" {
  source = "github.com/philips-labs/terraform-aws-github-oidc?ref=v0.6.0"

  openid_connect_provider_arn = module.oidc_provider.openid_connect_provider.arn
  repo                        = "SonarSource/sonar-cpp"
  role_name                   = "sonar-source"
}

data "aws_iam_policy_document" "s3" {
  statement {
    actions   = ["s3:PutObject", "s3:GetObject", "s3:DeleteObject"]
    resources = ["${aws_s3_bucket.compiler-explorer.arn}/opt-nonfree/sonar/*"]
  }
}

resource "aws_iam_role_policy" "s3" {
  name   = "s3-policy"
  role   = module.oidc_repo_sonar_source.role.name
  policy = data.aws_iam_policy_document.s3.json
}
