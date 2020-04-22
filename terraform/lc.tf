locals {
  image_id          = "ami-02ac4e107a7ebfd3c"
  staging_image_id  = "ami-02ac4e107a7ebfd3c"
  beta_image_id     = "ami-02ac4e107a7ebfd3c"
  staging_user_data = base64encode("staging")
  beta_user_data    = base64encode("beta")
  // Current c5 on-demand price is 0.085. Yearly pre-pay is 0.05 (so this is same as prepaying a year)
  // Historically we pay ~ 0.035
  spot_price        = "0.05"
}

resource "aws_launch_configuration" "CompilerExplorer-beta-large" {
  lifecycle {
    create_before_destroy = true
  }

  name_prefix                 = "compiler-explorer-beta-large"
  image_id                    = local.beta_image_id
  instance_type               = "c5.large"
  iam_instance_profile        = aws_iam_instance_profile.CompilerExplorerRole.name
  key_name                    = "mattgodbolt"
  security_groups             = [aws_security_group.CompilerExplorer.id]
  associate_public_ip_address = true
  user_data                   = local.beta_user_data
  enable_monitoring           = false
  ebs_optimized               = true
  spot_price                  = local.spot_price

  root_block_device {
    volume_type           = "gp2"
    volume_size           = 10
    delete_on_termination = true
  }
}

resource "aws_launch_configuration" "CompilerExplorer-staging" {
  lifecycle {
    create_before_destroy = true
  }

  name_prefix                 = "compiler-explorer-staging"
  image_id                    = local.staging_image_id
  instance_type               = "c5.large"
  iam_instance_profile        = aws_iam_instance_profile.CompilerExplorerRole.name
  key_name                    = "mattgodbolt"
  security_groups             = [aws_security_group.CompilerExplorer.id]
  associate_public_ip_address = true
  user_data                   = local.staging_user_data
  enable_monitoring           = false
  ebs_optimized               = true
  spot_price                  = local.spot_price

  root_block_device {
    volume_type           = "gp2"
    volume_size           = 10
    delete_on_termination = true
  }
}

resource "aws_launch_configuration" "CompilerExplorer-prod-spot-large" {
  lifecycle {
    create_before_destroy = true
  }

  name_prefix                 = "compiler-explorer-prod-large"
  image_id                    = local.image_id
  instance_type               = "c5.large"
  iam_instance_profile        = aws_iam_instance_profile.CompilerExplorerRole.name
  key_name                    = "mattgodbolt"
  security_groups             = [aws_security_group.CompilerExplorer.id]
  associate_public_ip_address = true
  enable_monitoring           = false
  ebs_optimized               = true
  spot_price                  = local.spot_price

  root_block_device {
    volume_type           = "gp2"
    volume_size           = 10
    delete_on_termination = true
  }
}

resource "aws_launch_configuration" "CompilerExplorer-prod-t3" {
  lifecycle {
    create_before_destroy = true
  }

  name_prefix                 = "compiler-explorer-prod-t3"
  image_id                    = local.image_id
  instance_type               = "t3.medium"
  iam_instance_profile        = aws_iam_instance_profile.CompilerExplorerRole.name
  key_name                    = "mattgodbolt"
  security_groups             = [aws_security_group.CompilerExplorer.id]
  associate_public_ip_address = true
  enable_monitoring           = false
  ebs_optimized               = false

  root_block_device {
    volume_type           = "gp2"
    volume_size           = 10
    delete_on_termination = true
  }
}
