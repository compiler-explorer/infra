packer {
  required_plugins {
    amazon = {
      source  = "github.com/hashicorp/amazon"
      version = "~> 1"
    }
  }
}

variable "MY_ACCESS_KEY" {
  type    = string
  default = ""
}

variable "MY_SECRET_KEY" {
  type    = string
  default = ""
}

data "amazon-ami" "bionic" {
  access_key = "${var.MY_ACCESS_KEY}"
  filters = {
    name                = "ubuntu/images/*ubuntu-bionic-18.04-amd64-server-*"
    root-device-type    = "ebs"
    virtualization-type = "hvm"
  }
  most_recent = true
  owners      = ["099720109477"]
  region      = "us-east-1"
  secret_key  = "${var.MY_SECRET_KEY}"
}

locals { timestamp = regex_replace(timestamp(), "[- TZ:]", "") }

source "amazon-ebs" "bionic" {
  access_key = "${var.MY_ACCESS_KEY}"
  ami_block_device_mappings {
    delete_on_termination = true
    device_name           = "/dev/sda1"
    volume_size           = 6
    volume_type           = "gp2"
  }
  ami_name                    = "ce-conan packer 18.04 @ ${local.timestamp}"
  associate_public_ip_address = true
  iam_instance_profile        = "XaniaBlog"
  instance_type               = "t3.medium"
  launch_block_device_mappings {
    delete_on_termination = true
    device_name           = "/dev/sda1"
    volume_size           = 10
    volume_type           = "gp2"
  }
  region            = "us-east-1"
  secret_key        = "${var.MY_SECRET_KEY}"
  security_group_id = "sg-f53f9f80"
  source_ami        = "${data.amazon-ami.bionic.id}"
  ssh_username      = "ubuntu"
  subnet_id         = "subnet-1df1e135"
  tags = {
    Site = "CompilerExplorer"
  }
  vpc_id = "vpc-17209172"
}

build {
  sources = ["source.amazon-ebs.bionic"]

  provisioner "file" {
    destination = "/home/ubuntu/"
    source      = "packer"
  }

  provisioner "shell" {
    execute_command = "{{ .Vars }} sudo -E bash '{{ .Path }}'"
    inline = [
      "set -euo pipefail",
      "while [ ! -f /var/lib/cloud/instance/boot-finished ]; do echo 'Waiting for cloud-init...'; sleep 1; done",
      "export DEBIAN_FRONTEND=noninteractive", "cp /home/ubuntu/packer/known_hosts /home/ubuntu/.ssh/",
      "rm -rf /home/ubuntu/packer", "apt-get -y update", "apt-get -y install git",
      "git clone https://github.com/compiler-explorer/infra.git /home/ubuntu/infra",
      "chown -R ubuntu:ubuntu /home/ubuntu/infra", "/home/ubuntu/infra/setup-conan.sh"
    ]
  }

}
