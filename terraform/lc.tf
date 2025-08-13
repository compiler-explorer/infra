locals {
  prod_image_id            = "ami-0898209aafa929263"
  staging_image_id         = "ami-0898209aafa929263"
  beta_image_id            = "ami-0898209aafa929263"
  gpu_image_id             = "ami-026c749706de56d71"
  aarch64prod_image_id     = "ami-0568490376b31f431"
  aarch64staging_image_id  = "ami-0568490376b31f431"
  winprod_image_id         = "ami-0cf55c2532ef41565"
  winstaging_image_id      = "ami-0cf55c2532ef41565"
  wintest_image_id         = "ami-0807541f025aad832"
  staging_user_data        = base64encode("staging")
  beta_user_data           = base64encode("envbeta")
  prod_user_data           = base64encode("prod")
  gpu_user_data            = base64encode("gpu")
  aarch64prod_user_data    = base64encode("aarch64prod")
  aarch64staging_user_data = base64encode("aarch64staging")
  winprod_user_data        = base64encode("winprod")
  winstaging_user_data     = base64encode("winstaging")
  wintest_user_data        = base64encode("wintest")

  launch_templates = {
    beta = {
      image_id      = local.beta_image_id
      user_data     = local.beta_user_data
      instance_type = "m5.large"
    }
    staging = {
      image_id      = local.staging_image_id
      user_data     = local.staging_user_data
      instance_type = "m5.large"
    }
    prod = {
      image_id      = local.prod_image_id
      user_data     = local.prod_user_data
      instance_type = "c6i.large"
    }
    "prod-gpu" = {
      image_id      = local.gpu_image_id
      user_data     = local.gpu_user_data
      instance_type = "g4dn.xlarge"
    }
    aarch64prod = {
      image_id      = local.aarch64prod_image_id
      user_data     = local.aarch64prod_user_data
      instance_type = "c7g.xlarge"
    }
    aarch64staging = {
      image_id      = local.aarch64staging_image_id
      user_data     = local.aarch64staging_user_data
      instance_type = "c7g.xlarge"
    }
    // Windows machines - ensure the key starts with "win"
    wintest = {
      image_id      = local.wintest_image_id
      user_data     = local.wintest_user_data
      instance_type = "c5ad.large"
    }
    winstaging = {
      image_id      = local.winstaging_image_id
      user_data     = local.winstaging_user_data
      instance_type = "m6i.large"
    }
    winprod = {
      image_id      = local.winprod_image_id
      user_data     = local.winprod_user_data
      instance_type = "m6i.large"
    }
  }
}

resource "aws_launch_template" "ce" {
  for_each = local.launch_templates

  name          = "ce-${each.key}"
  description   = "${title(each.key)} launch template"
  ebs_optimized = true

  iam_instance_profile {
    arn = startswith(each.key, "win") ? aws_iam_instance_profile.CompilerExplorerWindowsRole.arn : aws_iam_instance_profile.CompilerExplorerRole.arn
  }

  image_id               = each.value.image_id
  user_data              = each.value.user_data
  key_name               = "mattgodbolt"
  vpc_security_group_ids = [aws_security_group.CompilerExplorer.id]
  instance_type          = each.value.instance_type
  metadata_options {
    # once Windows has been updated to use Tokens...
    # http_tokens                 = "required"
    http_put_response_hop_limit = 1
    instance_metadata_tags      = "enabled"
  }
}
