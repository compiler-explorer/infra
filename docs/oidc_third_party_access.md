# OIDC Third-Party Repository Access

This document covers granting external repositories access to Compiler Explorer AWS resources using GitHub Actions OIDC authentication.

## Overview

We use OpenID Connect (OIDC) to allow GitHub Actions workflows in external repositories to authenticate with AWS and access specific S3 resources without storing long-lived credentials. The configuration is managed in `terraform/third_party.tf`.

## Configuration Pattern

Each external repository gets its own OIDC module configuration:

```hcl
module "oidc_repo_example" {
  source = "github.com/philips-labs/terraform-aws-github-oidc?ref=v0.8.1"

  openid_connect_provider_arn = module.oidc_provider.openid_connect_provider.arn
  repo                        = "org/repository-name"
  role_name                   = "example-role"

  default_conditions = ["allow_all"]  # or ["allow_main"]
}
```

The `default_conditions` setting controls which Git references can authenticate:
- `allow_main`: Only the main branch
- `allow_all`: Any branch, tag, or pull request

## Required GitHub Actions Setup

External repositories must configure their workflows with:

```yaml
permissions:
  id-token: write
  contents: read

steps:
  - uses: aws-actions/configure-aws-credentials@v4
    with:
      role-to-assume: arn:aws:iam::052730242331:role/github-actions/ROLE_NAME
      aws-region: us-east-1
```

## Debugging Authentication Failures

When external parties report "Not authorized to perform sts:AssumeRoleWithWebIdentity" errors:

### 1. Check Recent Authentication Attempts

```bash
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=EventName,AttributeValue=AssumeRoleWithWebIdentity \
  --query 'Events[?contains(CloudTrailEvent, `ROLE_NAME`)].{Time:EventTime, User:Username}' \
  --output table
```

The `User` field shows the actual subject claim from GitHub (e.g., `repo:org/repo:ref:refs/tags/v1.0`).

### 2. Verify Current Trust Policy

```bash
aws iam get-role --role-name ROLE_NAME \
  --query 'Role.AssumeRolePolicyDocument' \
  --output json | jq .
```

### 3. Check Terraform State

```bash
cd terraform
terraform state show 'module.oidc_repo_EXAMPLE.aws_iam_role.main[0]' | grep -A 30 "assume_role_policy"
```

## Common Issues

**Tag-based workflows failing**: If workflows trigger on tag pushes but the trust policy uses `allow_main`, authentication will fail because the subject claim contains `refs/tags/*` instead of `refs/heads/main`. Change `default_conditions` to `["allow_all"]`.

**Repository name mismatch**: The `repo` field in terraform must exactly match the GitHub repository name. Check recent commits for any repository name changes.

**Missing permissions**: GitHub Actions workflows must include `id-token: write` permission.

**Incorrect role ARN**: The role ARN must include the path `/github-actions/` as created by the terraform module.
