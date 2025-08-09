packer {
  required_plugins {
    amazon = {
      source  = "github.com/hashicorp/amazon"
      version = "~> 1"
    }
  }
}

variable "BRANCH" {
  type    = string
  default = "main"
}

variable "MY_ACCESS_KEY" {
  type    = string
  default = ""
}

variable "MY_SECRET_KEY" {
  type    = string
  default = ""
}

data "amazon-ami" "ubuntu" {
  access_key = "${var.MY_ACCESS_KEY}"
  filters = {
    // needs non-minimal for now annoyingly else nvidia drivers fail to install:
    // Building module(s)....................(bad exit status: 2)
    // Failed command:
    // 'make' -j4 KERNEL_UNAME=6.8.0-1033-aws IGNORE_CC_MISMATCH=1 SYSSRC=/lib/modules/6.8.0-1033-aws/build LD=/u
    // Error! Bad return status for module build on kernel: 6.8.0-1033-aws (x86_64)
    // Consult /var/lib/dkms/nvidia/570.172.08/build/make.log for more information.
    // dpkg: error processing package nvidia-dkms-570-open (--configure):
    // installed nvidia-dkms-570-open package post-installation script subprocess returned error exit status 10

    name                = "ubuntu/images/*ubuntu-*-22.04-amd64-*"
    root-device-type    = "ebs"
    virtualization-type = "hvm"
  }
  most_recent = true
  owners      = ["099720109477"]
  region      = "us-east-1"
  secret_key  = "${var.MY_SECRET_KEY}"
}

locals { timestamp = regex_replace(timestamp(), "[- TZ:]", "") }

source "amazon-ebs" "ubuntu" {
  access_key = "${var.MY_ACCESS_KEY}"
  ami_name                    = "compiler-explorer gpu packer @ ${local.timestamp}"
  associate_public_ip_address = true
  iam_instance_profile        = "XaniaBlog"
  instance_type               = "g4dn.xlarge"
  launch_block_device_mappings {
    delete_on_termination = true
    device_name           = "/dev/sda1"
    volume_size           = 24
    volume_type           = "gp2"
  }
  region = "us-east-1"
  run_volume_tags = {
    Site = "CompilerExplorer"
  }
  secret_key        = "${var.MY_SECRET_KEY}"
  security_group_id = "sg-f53f9f80"
  source_ami        = "${data.amazon-ami.ubuntu.id}"
  ssh_username      = "ubuntu"
  subnet_id         = "subnet-1df1e135"
  tags = {
    Site = "CompilerExplorer"
  }
  vpc_id = "vpc-17209172"
}

build {
  sources = ["source.amazon-ebs.ubuntu"]

  provisioner "file" {
    destination = "/home/ubuntu/"
    source      = "packer"
  }

  provisioner "shell" {
    execute_command = "{{ .Vars }} sudo -E bash '{{ .Path }}'"
    inline = [
      "set -euo pipefail",
      "cloud-init status --wait",
      "export DEBIAN_FRONTEND=noninteractive", "mkdir -p /root/.ssh",
      "cp /home/ubuntu/packer/known_hosts /root/.ssh/", "cp /home/ubuntu/packer/known_hosts /home/ubuntu/.ssh/",
      "rm -rf /home/ubuntu/packer", "apt-get -y update", "apt-get -y install git",
      "git clone -b ${var.BRANCH} https://github.com/compiler-explorer/infra.git /infra", "cd /infra",
      "env PACKER_SETUP=yes bash setup-gpu-node.sh 2>&1 | tee /tmp/setup.log"
    ]
  }

}
