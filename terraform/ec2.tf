locals {
  runner_image_id        = "ami-05d4fb32368117b54"
  gpu_runner_image_id    = "ami-05df317ba6d2893be"
  conan_image_id         = "ami-0243961999a0be147"
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
    volume_type           = "gp3"
    volume_size           = 100
    delete_on_termination = false
  }

  tags = {
    Name        = "AdminNode"
    Environment = "admin"
  }

  volume_tags = {
    Name = "AdminNodeVolume"
    Site = "CompilerExplorer"
  }

  metadata_options {
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
    instance_metadata_tags      = "enabled"
  }
}

resource "aws_instance" "ConanNode" {
  ami                         = local.conan_image_id
  iam_instance_profile        = aws_iam_instance_profile.CompilerExplorerRole.name
  ebs_optimized               = false
  instance_type               = "t3a.small"
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
    Name        = "ConanNode"
    Environment = "conan"
  }

  volume_tags = {
    Name = "ConanNodeRoot"
    Site = "CompilerExplorer"
  }

  metadata_options {
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
    instance_metadata_tags      = "enabled"
  }
}

# The conan-server data volume. Holds /home/ce/.conan_server (the conan
# package store) and conanproxy's buildslogs.db. This is the single piece
# of irreplaceable state on the conan-node -- everything else can be re-baked
# from packer. prevent_destroy guards against an accidental terraform destroy
# wiping the volume out; routine instance replacements detach/reattach via
# aws_volume_attachment.ebs_conanserver below and don't touch this resource.
resource "aws_ebs_volume" "conan_data" {
  availability_zone = "us-east-1a"
  size              = 600
  type              = "gp2"
  encrypted         = false

  tags = {
    Name = "CEConanServerVol1"
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_volume_attachment" "ebs_conanserver" {
  device_name = "/dev/xvdb"
  volume_id   = aws_ebs_volume.conan_data.id
  instance_id = aws_instance.ConanNode.id
  # Have terraform stop the instance (ACPI shutdown -> graceful systemd
  # unmount of /home/ce/.conan_server) before detaching the data volume.
  # Without this, destroy of this resource on an in-use volume hangs.
  stop_instance_before_detaching = true
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
    Name        = "CERunner"
    Environment = "runner"
  }
  metadata_options {
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
    instance_metadata_tags      = "enabled"
  }

}

resource "aws_instance" "CEGPURunner" {
  ami                         = local.gpu_runner_image_id
  iam_instance_profile        = aws_iam_instance_profile.CompilerExplorerRole.name
  ebs_optimized               = false
  instance_type               = "g4dn.xlarge"
  monitoring                  = false
  key_name                    = "mattgodbolt"
  subnet_id                   = local.admin_subnet
  vpc_security_group_ids      = [aws_security_group.CompilerExplorer.id]
  associate_public_ip_address = true
  source_dest_check           = false

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
    Name        = "CEGPURunner"
    Environment = "gpu-runner"
  }
  metadata_options {
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
    instance_metadata_tags      = "enabled"
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

  root_block_device {
    volume_type           = "gp2"
    volume_size           = 150
    delete_on_termination = true
  }

  lifecycle {
    ignore_changes = [
      // Seemingly needed to not replace stopped instances
      associate_public_ip_address,
      // user_data was removed in favour of Environment tag, but rather than replace
      // the instance to clear the drift, we're ignoring it. Remove this if the
      // instance is ever rebuilt.
      user_data,
    ]
  }

  tags = {
    Name        = "CESMBServer"
    Environment = "smbserver"
  }
  metadata_options {
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
    instance_metadata_tags      = "enabled"
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
//    Environment = "smbserver"
//  }
//   metadata_options {
//   http_tokens                 = "required"
//   http_put_response_hop_limit = 1
//   instance_metadata_tags      = "enabled"
// }
//}

//resource "aws_instance" "elfshaker" {
//  ami                         = "ami-0b97d4bbd77733fc0"
//  iam_instance_profile        = aws_iam_instance_profile.CompilerExplorerRole.name // TODO
//  instance_type               = "t4g.2xlarge"
//  monitoring                  = false
//  key_name                    = "pwaller"                                                        // TODO
//  subnet_id                   = "subnet-1bed1d42"                                                // TODO local.admin_subnet
//  vpc_security_group_ids      = [aws_security_group.CompilerExplorer.id, "sg-0451c2db0fa8005ca"] // TODO
//  associate_public_ip_address = true
//  user_data                   = <<EOF
//{ pkgs, modulesPath, ... }: {
//  imports = [ "$${modulesPath}/virtualisation/amazon-image.nix" ];
//  ec2.efi = true;
//
//  environment.systemPackages = with pkgs; [ vim nfs-utils htop tmux dool nix-output-monitor git patchelf bintools ];
//  nix.settings.extra-experimental-features = "flakes nix-command";
//
//  users.users.root.openssh.authorizedKeys.keys = [
//    "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFBzJtdBiXHs5qV2k9IaIDlOZiIHss4aeOW7bGGAu7Us pwaller"
//  ];
//
//  fileSystems."/mnt/manyclangs" = {
//    fsType = "nfs4";
//    device = "fs-db4c8192.efs.us-east-1.amazonaws.com:/manyclangs";
//    options = [ "noresvport" "rsize=1048576" "wsize=1048576" "hard" "timeo=600" "retrans=2" "_netdev" "nofail" ];
//  };
//
//  programs.nix-ld.enable = true;
//  programs.nix-ld.libraries = with pkgs; [
//    stdenv.cc.cc
//  ];
//}
//EOF
//
//  root_block_device {
//    volume_type           = "gp3"
//    volume_size           = 100
//    delete_on_termination = false
//  }
//
//  tags = {
//    Name        = "ElfShaker"
//    Environment = "elfshaker"
//  }
//
//  volume_tags = {
//    Name = "ElfShaker"
//    Site = "CompilerExplorer"
//  }
//
//  metadata_options {
//    http_tokens                 = "required"
//    http_put_response_hop_limit = 1
//    instance_metadata_tags      = "enabled"
//  }
//}
