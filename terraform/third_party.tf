module "oidc_provider" {
  source = "github.com/philips-labs/terraform-aws-github-oidc//modules/provider?ref=v0.8.1"
}

module "oidc_repo_sonar_source" {
  source = "github.com/philips-labs/terraform-aws-github-oidc?ref=v0.8.1"

  openid_connect_provider_arn = module.oidc_provider.openid_connect_provider.arn
  repo                        = "SonarSource/sonar-cpp"
  role_name                   = "SonarSource"

  default_conditions = ["allow_all"]

  # Restrict to just 'master' (the SS repo uses this and the oidc provider only supports 'main')
  conditions = [{
    test     = "StringLike"
    variable = "token.actions.githubusercontent.com:sub"
    values   = ["repo:SonarSource/sonar-cpp:ref:refs/heads/master"]
  }]
}

data "aws_iam_policy_document" "s3_sonar" {
  statement {
    actions   = ["s3:PutObject", "s3:GetObject", "s3:DeleteObject"]
    resources = ["${aws_s3_bucket.compiler-explorer.arn}/opt-nonfree/sonar/*"]
  }
}

resource "aws_iam_role_policy" "s3_sonar" {
  name   = "s3-policy"
  role   = module.oidc_repo_sonar_source.role.name
  policy = data.aws_iam_policy_document.s3_sonar.json
}

module "oidc_repo_brontosource" {
  source = "github.com/philips-labs/terraform-aws-github-oidc?ref=v0.8.1"

  openid_connect_provider_arn = module.oidc_provider.openid_connect_provider.arn
  repo                        = "brontosource/bin"
  role_name                   = "brontosource"

  default_conditions = ["allow_main"]
}

data "aws_iam_policy_document" "s3_bronto" {
  statement {
    actions   = ["s3:PutObject", "s3:GetObject", "s3:DeleteObject"]
    resources = ["${aws_s3_bucket.compiler-explorer.arn}/opt-nonfree/brontosource/*"]
  }
}

resource "aws_iam_role_policy" "s3_bronto" {
  name   = "s3-policy"
  role   = module.oidc_repo_brontosource.role.name
  policy = data.aws_iam_policy_document.s3_bronto.json
}

# Not really third party but
module "oidc_repo_explain" {
  source = "github.com/philips-labs/terraform-aws-github-oidc?ref=v0.8.1"

  openid_connect_provider_arn = module.oidc_provider.openid_connect_provider.arn
  repo                        = "compiler-explorer/explain"
  role_name                   = "explain-ci"

  default_conditions = ["allow_main"]
}

data "aws_iam_policy_document" "ce_explain" {
  # ECR public
  statement {
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }
  statement {
    actions = [
        "ecr:BatchGetImage",
        "ecr:BatchCheckLayerAvailability",
        "ecr:CompleteLayerUpload",
        "ecr:GetDownloadUrlForLayer",
        "ecr:InitiateLayerUpload",
        "ecr:PutImage",
        "ecr:UploadLayerPart"    ]
    resources = [aws_ecr_repository.explain.arn]
  }
}

resource "aws_iam_role_policy" "ce_explain" {
  name   = "ce-explain-policy"
  role   = module.oidc_repo_explain.role.name
  policy = data.aws_iam_policy_document.ce_explain.json
}
