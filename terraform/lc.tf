locals {
  image_id                 = "ami-0e8dc79a8b7ecccaa"
  staging_image_id         = "ami-0e8dc79a8b7ecccaa"
  beta_image_id            = "ami-0e8dc79a8b7ecccaa"
  gpu_image_id             = "ami-09e85330c7a5c8afb"
  aarch64prod_image_id     = "ami-079d9b1e36db465bb"
  aarch64staging_image_id  = "ami-079d9b1e36db465bb"
  winprod_image_id         = "ami-0807541f025aad832"
  winstaging_image_id      = "ami-0807541f025aad832"
  wintest_image_id         = "ami-0807541f025aad832"
  staging_user_data        = base64encode("staging")
  beta_user_data           = base64encode("beta")
  gpu_user_data            = base64encode("gpu")
  aarch64prod_user_data    = base64encode("aarch64prod")
  aarch64staging_user_data = base64encode("aarch64staging")
  winprod_user_data        = base64encode("winprod")
  winstaging_user_data     = base64encode("winstaging")
  wintest_user_data        = base64encode("wintest")
}

resource "aws_launch_template" "CompilerExplorer-beta" {
  name          = "ce-beta"
  description   = "Beta launch template"
  ebs_optimized = true
  iam_instance_profile {
    arn = aws_iam_instance_profile.CompilerExplorerRole.arn
  }
  image_id               = local.beta_image_id
  user_data              = local.beta_user_data
  key_name               = "mattgodbolt"
  vpc_security_group_ids = [aws_security_group.CompilerExplorer.id]
  instance_type          = "m5.large"

  tag_specifications {
    resource_type = "volume"

    tags = {
      Site        = "CompilerExplorer"
      Environment = "Beta"
    }
  }

  tag_specifications {
    resource_type = "instance"

    tags = {
      Site        = "CompilerExplorer"
      Environment = "Beta"
      Name        = "Beta"
    }
  }
}

resource "aws_launch_template" "CompilerExplorer-staging" {
  name          = "ce-staging"
  description   = "Staging launch template"
  ebs_optimized = true
  iam_instance_profile {
    arn = aws_iam_instance_profile.CompilerExplorerRole.arn
  }
  image_id               = local.staging_image_id
  user_data              = local.staging_user_data
  key_name               = "mattgodbolt"
  vpc_security_group_ids = [aws_security_group.CompilerExplorer.id]
  instance_type          = "m5.large"

  tag_specifications {
    resource_type = "volume"

    tags = {
      Site        = "CompilerExplorer"
      Environment = "Staging"
    }
  }

  tag_specifications {
    resource_type = "instance"

    tags = {
      Site        = "CompilerExplorer"
      Environment = "Staging"
      Name        = "Staging"
    }
  }
}

resource "aws_launch_template" "CompilerExplorer-prod-gpu" {
  name          = "ce-prod-gpu"
  description   = "Prod GPU launch template"
  ebs_optimized = true
  iam_instance_profile {
    arn = aws_iam_instance_profile.CompilerExplorerRole.arn
  }
  image_id               = local.gpu_image_id
  user_data              = local.gpu_user_data
  key_name               = "mattgodbolt"
  vpc_security_group_ids = [aws_security_group.CompilerExplorer.id]
  instance_type          = "g4dn.xlarge"

  tag_specifications {
    resource_type = "volume"

    tags = {
      Site        = "CompilerExplorer"
      Environment = "GPU"
    }
  }

  tag_specifications {
    resource_type = "instance"

    tags = {
      Site        = "CompilerExplorer"
      Environment = "GPU"
      Name        = "GPU"
    }
  }
}

resource "aws_launch_template" "CompilerExplorer-aarch64prod" {
  name          = "ce-aarch64prod"
  description   = "Prod Aarch64 launch template"
  ebs_optimized = true
  iam_instance_profile {
    arn = aws_iam_instance_profile.CompilerExplorerRole.arn
  }
  image_id               = local.aarch64prod_image_id
  user_data              = local.aarch64prod_user_data
  key_name               = "mattgodbolt"
  vpc_security_group_ids = [aws_security_group.CompilerExplorer.id]
  instance_type          = "c7g.xlarge"

  tag_specifications {
    resource_type = "volume"

    tags = {
      Site        = "CompilerExplorer"
      Environment = "AARCH64prod"
    }
  }

  tag_specifications {
    resource_type = "instance"

    tags = {
      Site        = "CompilerExplorer"
      Environment = "AARCH64prod"
      Name        = "AARCH64prod"
    }
  }
}

resource "aws_launch_template" "CompilerExplorer-aarch64staging" {
  name          = "ce-aarch64staging"
  description   = "Staging Aarch64 launch template"
  ebs_optimized = true
  iam_instance_profile {
    arn = aws_iam_instance_profile.CompilerExplorerRole.arn
  }
  image_id               = local.aarch64staging_image_id
  user_data              = local.aarch64staging_user_data
  key_name               = "mattgodbolt"
  vpc_security_group_ids = [aws_security_group.CompilerExplorer.id]
  instance_type          = "c7g.xlarge"

  tag_specifications {
    resource_type = "volume"

    tags = {
      Site        = "CompilerExplorer"
      Environment = "AARCH64staging"
    }
  }

  tag_specifications {
    resource_type = "instance"

    tags = {
      Site        = "CompilerExplorer"
      Environment = "AARCH64staging"
      Name        = "AARCH64staging"
    }
  }
}

resource "aws_launch_template" "CompilerExplorer-prod" {
  name          = "ce-prod"
  description   = "Production launch template"
  ebs_optimized = true
  iam_instance_profile {
    arn = aws_iam_instance_profile.CompilerExplorerRole.arn
  }
  image_id               = local.image_id
  key_name               = "mattgodbolt"
  vpc_security_group_ids = [aws_security_group.CompilerExplorer.id]
  instance_type          = "c6i.large" // This is overridden in the ASG

  tag_specifications {
    resource_type = "volume"

    tags = {
      Site = "CompilerExplorer"
    }
  }

  tag_specifications {
    resource_type = "instance"

    tags = {
      Site        = "CompilerExplorer"
      Environment = "Prod"
      Name        = "Prod"
    }
  }
}

resource "aws_launch_template" "CompilerExplorer-wintest" {
  name          = "ce-wintest"
  description   = "WinTest launch template"
  ebs_optimized = true
  iam_instance_profile {
    arn = aws_iam_instance_profile.CompilerExplorerWindowsRole.arn
  }
  image_id               = local.wintest_image_id
  key_name               = "mattgodbolt"
  vpc_security_group_ids = [aws_security_group.CompilerExplorer.id]
  instance_type          = "c5ad.large"
  user_data              = local.wintest_user_data

  tag_specifications {
    resource_type = "volume"

    tags = {
      Site = "CompilerExplorer"
    }
  }

  tag_specifications {
    resource_type = "instance"

    tags = {
      Site        = "CompilerExplorer"
      Environment = "Wintest"
      Name        = "Wintest"
    }
  }
}

resource "aws_launch_template" "CompilerExplorer-winstaging" {
  name          = "ce-winstaging"
  description   = "WinStaging launch template"
  ebs_optimized = true
  iam_instance_profile {
    arn = aws_iam_instance_profile.CompilerExplorerWindowsRole.arn
  }
  image_id               = local.winstaging_image_id
  key_name               = "mattgodbolt"
  vpc_security_group_ids = [aws_security_group.CompilerExplorer.id]
  instance_type          = "m6i.large"
  user_data              = local.winstaging_user_data

  tag_specifications {
    resource_type = "volume"

    tags = {
      Site = "CompilerExplorer"
    }
  }

  tag_specifications {
    resource_type = "instance"

    tags = {
      Site        = "CompilerExplorer"
      Environment = "Winstaging"
      Name        = "Winstaging"
    }
  }
}

resource "aws_launch_template" "CompilerExplorer-winprod" {
  name          = "ce-winprod"
  description   = "WinProd launch template"
  ebs_optimized = true
  iam_instance_profile {
    arn = aws_iam_instance_profile.CompilerExplorerWindowsRole.arn
  }
  image_id               = local.winprod_image_id
  key_name               = "mattgodbolt"
  vpc_security_group_ids = [aws_security_group.CompilerExplorer.id]
  instance_type          = "m6i.large" // This is overridden in the ASG
  user_data              = local.winprod_user_data

  tag_specifications {
    resource_type = "volume"

    tags = {
      Site = "CompilerExplorer"
    }
  }

  tag_specifications {
    resource_type = "instance"

    tags = {
      Site        = "CompilerExplorer"
      Environment = "Winprod"
      Name        = "Winprod"
    }
  }
}
