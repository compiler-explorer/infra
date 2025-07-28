locals {
  runner_image_id        = "ami-0a1472d1b7c289619"
  conan_image_id         = "ami-0b41dc7a318b530bd"
  builder_image_id       = "ami-0ef4921e9d82c03fb"
  smbserver_image_id     = "ami-01e7c7963a9c4755d"
  smbtestserver_image_id = "ami-0284c821376912369"
  admin_subnet           = module.ce_network.subnet["1a"].id
}

resource "aws_instance" "AdminNode" {
  ami                         = "ami-0e76b49ef537405f1"
  iam_instance_profile        = aws_iam_instance_profile.CompilerExplorerAdminNode.name
  ebs_optimized               = false
  instance_type               = "m6a.large"
  monitoring                  = false
  key_name                    = "mattgodbolt"
  subnet_id                   = local.admin_subnet
  vpc_security_group_ids      = [aws_security_group.AdminNode.id]
  associate_public_ip_address = true
  source_dest_check           = true

  root_block_device {
    volume_type           = "gp2"
    volume_size           = 40
    delete_on_termination = false
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
  instance_type               = "t3.micro"
  monitoring                  = false
  key_name                    = "mattgodbolt"
  subnet_id                   = local.admin_subnet
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
  iam_instance_profile        = aws_iam_instance_profile.Builder.name
  ebs_optimized               = true
  instance_type               = "c5d.4xlarge"
  monitoring                  = false
  key_name                    = "mattgodbolt"
  subnet_id                   = local.admin_subnet
  vpc_security_group_ids      = [aws_security_group.Builder.id]
  associate_public_ip_address = true
  source_dest_check           = false
  user_data                   = "builder"

  root_block_device {
    volume_type           = "gp2"
    volume_size           = 24
    delete_on_termination = true
  }

  lifecycle {
    ignore_changes = [
      // Seemingly needed to not replace stopped instances
      associate_public_ip_address
    ]
  }

  tags = {
    Name = "Builder"
  }
}

resource "aws_instance" "CERunner" {
  ami                         = local.runner_image_id
  iam_instance_profile        = aws_iam_instance_profile.CompilerExplorerRole.name
  ebs_optimized               = false
  instance_type               = "c5.xlarge"
  monitoring                  = false
  key_name                    = "mattgodbolt"
  subnet_id                   = local.admin_subnet
  vpc_security_group_ids      = [aws_security_group.CompilerExplorer.id]
  associate_public_ip_address = true
  source_dest_check           = false
  user_data                   = "runner"

  root_block_device {
    volume_type           = "gp2"
    volume_size           = 24
    delete_on_termination = true
  }

  lifecycle {
    ignore_changes = [
      // Seemingly needed to not replace stopped instances
      associate_public_ip_address
    ]
  }

  tags = {
    Name = "CERunner"
  }
}

resource "aws_instance" "CESMBServer" {
  ami                         = local.smbserver_image_id
  iam_instance_profile        = aws_iam_instance_profile.CompilerExplorerRole.name
  ebs_optimized               = false
  instance_type               = "t4g.micro"
  monitoring                  = false
  key_name                    = "mattgodbolt"
  subnet_id                   = local.admin_subnet
  vpc_security_group_ids      = [aws_security_group.CompilerExplorer.id]
  associate_public_ip_address = true
  source_dest_check           = false
  user_data                   = "smbserver"

  root_block_device {
    volume_type           = "gp2"
    volume_size           = 150
    delete_on_termination = true
  }

  lifecycle {
    ignore_changes = [
      // Seemingly needed to not replace stopped instances
      associate_public_ip_address
    ]
  }

  tags = {
    Name = "CESMBServer"
  }
}

//resource "aws_instance" "CESMBTestServer" {
//  ami                         = local.smbtestserver_image_id
//  iam_instance_profile        = aws_iam_instance_profile.CompilerExplorerRole.name
//  ebs_optimized               = false
//  instance_type               = "t4g.micro"
//  monitoring                  = false
//  key_name                    = "mattgodbolt"
//  subnet_id                   = local.admin_subnet
//  vpc_security_group_ids      = [aws_security_group.CompilerExplorer.id]
//  associate_public_ip_address = true
//  source_dest_check           = false
//  user_data                   = "smbserver"
//
//  root_block_device {
//    volume_type           = "gp2"
//    volume_size           = 100
//    delete_on_termination = true
//  }
//
//  lifecycle {
//    ignore_changes = [
//      // Seemingly needed to not replace stopped instances
//      associate_public_ip_address
//    ]
//  }
//
//  tags = {
//    Name = "CESMBTestServer"
//  }
//}

resource "aws_instance" "elfshaker" {
  ami                         = "ami-0b97d4bbd77733fc0"
  iam_instance_profile        = aws_iam_instance_profile.CompilerExplorerRole.name // TODO
  instance_type               = "t4g.2xlarge"
  monitoring                  = false
  key_name                    = "pwaller"                                                        // TODO
  subnet_id                   = "subnet-1bed1d42"                                                // TODO local.admin_subnet
  vpc_security_group_ids      = [aws_security_group.CompilerExplorer.id, "sg-0451c2db0fa8005ca"] // TODO
  associate_public_ip_address = true
  user_data                   = <<EOF
{ pkgs, modulesPath, ... }: {
  imports = [ "$${modulesPath}/virtualisation/amazon-image.nix" ];
  ec2.efi = true;

  environment.systemPackages = with pkgs; [ vim nfs-utils htop tmux dool nix-output-monitor git patchelf bintools ];
  nix.settings.extra-experimental-features = "flakes nix-command";

  users.users.root.openssh.authorizedKeys.keys = [
    "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFBzJtdBiXHs5qV2k9IaIDlOZiIHss4aeOW7bGGAu7Us pwaller"
  ];

  fileSystems."/mnt/manyclangs" = {
    fsType = "nfs4";
    device = "fs-db4c8192.efs.us-east-1.amazonaws.com:/manyclangs";
    options = [ "noresvport" "rsize=1048576" "wsize=1048576" "hard" "timeo=600" "retrans=2" "_netdev" "nofail" ];
  };

  programs.nix-ld.enable = true;
  programs.nix-ld.libraries = with pkgs; [
    stdenv.cc.cc
  ];
}
EOF

  root_block_device {
    volume_type           = "gp3"
    volume_size           = 100
    delete_on_termination = false
  }

  tags = {
    Name = "ElfShaker"
  }

  volume_tags = {
    Name = "ElfShaker"
    Site = "CompilerExplorer"
  }
}
