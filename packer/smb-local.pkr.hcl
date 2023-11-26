packer {
  required_plugins {
    docker = {
      source  = "github.com/hashicorp/docker"
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

source "docker" "focal" {
  commit = true
  image  = "ubuntu:20.04"
}

build {
  sources = ["source.docker.focal"]

  provisioner "shell" {
    inline = [
      "useradd ubuntu", "usermod -aG sudo ubuntu", "mkdir -p /home/ubuntu/.ssh", "chown -R ubuntu /home/ubuntu",
      "mkdir -p /root/.aws", "echo '[default]' > /root/.aws/config",
      "echo 'region=us-east-1' >> /root/.aws/config", "echo '[default]' > /root/.aws/credentials",
      "echo 'aws_access_key_id = ${var.MY_ACCESS_KEY}' >> /root/.aws/credentials",
      "echo 'aws_secret_access_key = ${var.MY_SECRET_KEY}' >> /root/.aws/credentials",
      "echo '# /opt here just to trick out the later scripts' >> /etc/fstab", "cat /root/.aws/credentials",
      "mkdir -p /opt/compiler-explorer"
    ]
  }

  provisioner "file" {
    destination = "/home/ubuntu/"
    source      = "."
  }

  provisioner "shell" {
    inline = [
      "set -e", "export DEBIAN_FRONTEND=noninteractive", "mkdir -p /root/.ssh", "export LOCALPACK=1",
      "cp /home/ubuntu/packer/known_hosts /root/.ssh/", "cp /home/ubuntu/packer/known_hosts /home/ubuntu/.ssh/",
      "rm -rf /home/ubuntu/packer", "apt-get -y update", "apt-get -y install git",
      "git clone -b ${var.BRANCH} https://github.com/compiler-explorer/infra.git /infra", "cd /infra",
      "env PACKER_SETUP=yes bash setup-smb.sh 2>&1 | tee /tmp/setup.log"
    ]
  }

}
