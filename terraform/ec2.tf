locals {
  conan_image_id   = "ami-0b41dc7a318b530bd"
  builder_image_id = "ami-0c4ea668b9465d57b"
}

resource "aws_instance" "AdminNode" {
  ami                         = "ami-0e76b49ef537405f1"
  iam_instance_profile        = "CompilerExplorerAdminNode"
  ebs_optimized               = false
  instance_type               = "t3.nano"
  monitoring                  = false
  key_name                    = "mattgodbolt"
  subnet_id                   = aws_subnet.ce-1a.id
  vpc_security_group_ids      = [aws_security_group.AdminNode.id]
  associate_public_ip_address = true
  source_dest_check           = true

  root_block_device {
    volume_type           = "gp2"
    volume_size           = 24
    delete_on_termination = true
  }

  tags = {
    Name = "AdminNode"
  }

  volume_tags = {
    Name = "AdminNodeVolume"
    Site = "CompilerExplorer"
  }
}

resource "aws_instance" "ConanNode" {
  ami                         = local.conan_image_id
  iam_instance_profile        = aws_iam_instance_profile.CompilerExplorerRole.name
  ebs_optimized               = false
  instance_type               = "t2.micro"
  monitoring                  = false
  key_name                    = "mattgodbolt"
  subnet_id                   = aws_subnet.ce-1a.id
  vpc_security_group_ids      = [aws_security_group.CompilerExplorer.id]
  associate_public_ip_address = true
  source_dest_check           = false

  root_block_device {
    volume_type           = "gp2"
    volume_size           = 10
    delete_on_termination = true
  }

  tags = {
    Name = "ConanNode"
  }

  volume_tags = {
    Name = "CEConanServerVol1"
    Site = "CompilerExplorer"
  }
}

resource "aws_volume_attachment" "ebs_conanserver" {
  device_name = "/dev/xvdb"
  volume_id   = "vol-0a99526fcf7bcfc11"
  instance_id = aws_instance.ConanNode.id
}


resource "aws_instance" "BuilderNode" {
  ami                         = local.builder_image_id
  // TODO bring into the fold
  iam_instance_profile        = "GccBuilder"
  ebs_optimized               = true
  // TODO make 4xlarge or similar
  instance_type               = "c5d.large"
  monitoring                  = false
  key_name                    = "mattgodbolt"
  subnet_id                   = aws_subnet.ce-1a.id
  // TODO reconsider, make an SG specifically for builder
  vpc_security_group_ids      = [aws_security_group.AdminNode.id]
  associate_public_ip_address = true
  source_dest_check           = false

  root_block_device {
    volume_type           = "gp2"
    volume_size           = 24
    delete_on_termination = true
  }

  tags = {
    Name = "Builder-New"
  }
}
