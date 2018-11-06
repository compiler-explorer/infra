locals {
  image_id = "ami-04cdfbf03ad8d818a"
  // "beta"
  beta_user_data = "YmV0YQ=="
}

resource "aws_launch_configuration" "CompilerExplorer-beta-c5" {
  lifecycle {
    create_before_destroy = true
  }

  name = "compiler-explorer-beta-c5"
  image_id = "${local.image_id}"
  instance_type = "c5.large"
  iam_instance_profile = "XaniaBlog"
  key_name = "mattgodbolt"
  security_groups = [
    "${aws_security_group.CompilerExplorer.id}"
  ]
  associate_public_ip_address = true
  user_data = "${local.beta_user_data}"
  enable_monitoring = false
  ebs_optimized = true
  spot_price = "0.05"

  root_block_device {
    volume_type = "gp2"
    volume_size = 10
    delete_on_termination = true
  }
}

resource "aws_launch_configuration" "CompilerExplorer-prod-c5" {
  lifecycle {
    create_before_destroy = true
  }

  name = "compiler-explorer-prod-c5"
  image_id = "${local.image_id}"
  instance_type = "c5.large"
  iam_instance_profile = "XaniaBlog"
  key_name = "mattgodbolt"
  security_groups = [
    "${aws_security_group.CompilerExplorer.id}"
  ]
  associate_public_ip_address = true
  enable_monitoring = false
  ebs_optimized = true
  spot_price = "0.05"

  root_block_device {
    volume_type = "gp2"
    volume_size = 10
    delete_on_termination = true
  }
}

resource "aws_launch_configuration" "CompilerExplorer-prod-t2" {
  lifecycle {
    create_before_destroy = true
  }

  name = "compiler-explorer-prod-t2"
  image_id = "${local.image_id}"
  instance_type = "t2.medium"
  iam_instance_profile = "XaniaBlog"
  key_name = "mattgodbolt"
  security_groups = [
    "${aws_security_group.CompilerExplorer.id}"
  ]
  associate_public_ip_address = true
  enable_monitoring = false
  ebs_optimized = false

  root_block_device {
    volume_type = "gp2"
    volume_size = 10
    delete_on_termination = true
  }
}