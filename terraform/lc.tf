locals {
  image_id                 = "ami-076fb669d8f6bad46"
  staging_image_id         = "ami-076fb669d8f6bad46"
  beta_image_id            = "ami-0714648404fb12346"
  gpu_image_id             = "ami-0fb76d685df82e159"
  aarch64prod_image_id     = "ami-024b4c0b3012cb09d"
  aarch64staging_image_id  = "ami-024b4c0b3012cb09d"
  winprod_image_id         = "ami-0807541f025aad832"
  winstaging_image_id      = "ami-0807541f025aad832"
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
      description   = "Beta launch template"
      image_id      = local.beta_image_id
      user_data     = local.beta_user_data
      instance_type = "m5.large"
      iam_role      = "linux"
      environment   = "Beta"
    }
    staging = {
      description   = "Staging launch template"
      image_id      = local.staging_image_id
      user_data     = local.staging_user_data
      instance_type = "m5.large"
      iam_role      = "linux"
      environment   = "Staging"
    }
    prod = {
      description   = "Production launch template"
      image_id      = local.image_id
      user_data     = local.prod_user_data
      instance_type = "c6i.large"
      iam_role      = "linux"
      environment   = "Prod"
    }
    "prod-gpu" = {
      description   = "Prod GPU launch template"
      image_id      = local.gpu_image_id
      user_data     = local.gpu_user_data
      instance_type = "g4dn.xlarge"
      iam_role      = "linux"
      environment   = "GPU"
    }
    aarch64prod = {
      description   = "Prod Aarch64 launch template"
      image_id      = local.aarch64prod_image_id
      user_data     = local.aarch64prod_user_data
      instance_type = "c7g.xlarge"
      iam_role      = "linux"
      environment   = "AARCH64prod"
    }
    aarch64staging = {
      description   = "Staging Aarch64 launch template"
      image_id      = local.aarch64staging_image_id
      user_data     = local.aarch64staging_user_data
      instance_type = "c7g.xlarge"
      iam_role      = "linux"
      environment   = "AARCH64staging"
    }
    wintest = {
      description   = "WinTest launch template"
      image_id      = local.wintest_image_id
      user_data     = local.wintest_user_data
      instance_type = "c5ad.large"
      iam_role      = "windows"
      environment   = "Wintest"
    }
    winstaging = {
      description   = "WinStaging launch template"
      image_id      = local.winstaging_image_id
      user_data     = local.winstaging_user_data
      instance_type = "m6i.large"
      iam_role      = "windows"
      environment   = "Winstaging"
    }
    winprod = {
      description   = "WinProd launch template"
      image_id      = local.winprod_image_id
      user_data     = local.winprod_user_data
      instance_type = "m6i.large"
      iam_role      = "windows"
      environment   = "Winprod"
    }
  }
}

resource "aws_launch_template" "ce" {
  for_each = local.launch_templates

  name          = "ce-${each.key}"
  description   = each.value.description
  ebs_optimized = true

  iam_instance_profile {
    arn = each.value.iam_role == "windows" ? aws_iam_instance_profile.CompilerExplorerWindowsRole.arn : aws_iam_instance_profile.CompilerExplorerRole.arn
  }

  image_id               = each.value.image_id
  user_data              = each.value.user_data
  key_name               = "mattgodbolt"
  vpc_security_group_ids = [aws_security_group.CompilerExplorer.id]
  instance_type          = each.value.instance_type

  tag_specifications {
    resource_type = "volume"

    tags = {
      Site        = "CompilerExplorer"
      Environment = each.value.environment
    }
  }

  tag_specifications {
    resource_type = "instance"

    tags = {
      Site        = "CompilerExplorer"
      Environment = each.value.environment
      Name        = each.value.environment
    }
  }
}
