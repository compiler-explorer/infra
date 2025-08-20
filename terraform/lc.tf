locals {
  prod_image_id           = "ami-03fc3889b720a5b82"
  staging_image_id        = "ami-03fc3889b720a5b82"
  beta_image_id           = "ami-03fc3889b720a5b82"
  gpu_image_id            = "ami-02b97134c4b0683aa"
  aarch64prod_image_id    = "ami-084b3ad993b0bd6b5"
  aarch64staging_image_id = "ami-084b3ad993b0bd6b5"
  winprod_image_id        = "ami-0cf55c2532ef41565"
  winstaging_image_id     = "ami-0cf55c2532ef41565"
  wintest_image_id        = "ami-0807541f025aad832"

  launch_templates = {
    prod = {
      image_id      = local.prod_image_id
      instance_type = "c6i.large"
    }
    staging = {
      image_id      = local.staging_image_id
      instance_type = "m5.large"
    }

    beta = {
      image_id      = local.beta_image_id
      instance_type = "m5.large"
    }
    "prod-gpu" = {
      image_id      = local.gpu_image_id
      instance_type = "g4dn.xlarge"
    }
    aarch64prod = {
      image_id      = local.aarch64prod_image_id
      instance_type = "c7g.xlarge"
    }
    aarch64staging = {
      image_id      = local.aarch64staging_image_id
      instance_type = "c7g.xlarge"
    }

    // Windows machines - ensure the key starts with "win"
    wintest = {
      image_id      = local.wintest_image_id
      instance_type = "c5ad.large"
    }
    winstaging = {
      image_id      = local.winstaging_image_id
      instance_type = "m6i.large"
    }
    winprod = {
      image_id      = local.winprod_image_id
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
  key_name               = "mattgodbolt"
  vpc_security_group_ids = [aws_security_group.CompilerExplorer.id]
  instance_type          = each.value.instance_type
  metadata_options {
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
    instance_metadata_tags      = "enabled"
  }
}
