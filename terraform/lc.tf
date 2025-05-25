locals {
  image_id                 = "ami-01297581addf1e7dd"
  staging_image_id         = "ami-01297581addf1e7dd"
  beta_image_id            = "ami-01297581addf1e7dd"
  gpu_image_id             = "ami-07ae9e39256e3ede7"
  aarch64prod_image_id     = "ami-07852229f17243f9c"
  aarch64staging_image_id  = "ami-07852229f17243f9c"
  winprod_image_id         = "ami-0b0cc698777995305"
  winstaging_image_id      = "ami-0b0cc698777995305"
  wintest_image_id         = "ami-0b0cc698777995305"
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
