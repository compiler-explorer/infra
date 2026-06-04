locals {
  prod_image_id           = "ami-04fdaafa4dfddcbba"
  staging_image_id        = "ami-04fdaafa4dfddcbba"
  beta_image_id           = "ami-04fdaafa4dfddcbba"
  gpu_image_id            = "ami-00ef1e7c67a0d611e"
  aarch64prod_image_id    = "ami-0eae356b0ea49abaf"
  aarch64staging_image_id = "ami-0eae356b0ea49abaf"
  winprod_image_id        = "ami-06f56d3eb81ab8177"
  winstaging_image_id     = "ami-06f56d3eb81ab8177"
  wintest_image_id        = "ami-0807541f025aad832"
  ce_router_image_id      = "ami-0d57d7a6a221012c5"

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

    // CE Router instances for compilation routing
    router = {
      image_id      = local.ce_router_image_id
      instance_type = "t4g.medium"
    }
  }
}

resource "aws_launch_template" "ce" {
  for_each = local.launch_templates

  name          = "ce-${each.key}"
  description   = "${title(each.key)} launch template"
  ebs_optimized = true

  iam_instance_profile {
    arn = startswith(each.key, "win") ? aws_iam_instance_profile.CompilerExplorerWindowsRole.arn : (each.key == "router" ? aws_iam_instance_profile.CeRouterRole.arn : aws_iam_instance_profile.CompilerExplorerRole.arn)
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
