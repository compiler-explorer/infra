#!/bin/bash

set -exuo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

env EXTRA_NFS_ARGS="" "${DIR}/setup-common.sh"

wget -qO- https://get.docker.com/ | sh
usermod -aG docker ubuntu

apt -y install mosh fish cronic subversion upx gdb
chsh ubuntu -s /usr/bin/fish

aws ssm get-parameter --name /admin/ce_private_key | jq -r .Parameter.Value >/home/ubuntu/.ssh/id_rsa
chmod 600 /home/ubuntu/.ssh/id_rsa
aws s3 cp s3://compiler-explorer/authorized_keys/admin.key /home/ubuntu/.ssh/id_rsa.pub
chown -R ubuntu:ubuntu /home/ubuntu/.ssh

sudo -u ubuntu fish setup.fish
crontab -u ubuntu crontab.builder

echo builder >/etc/hostname
hostname builder
sed -i "/127.0.0.1/c 127.0.0.1 localhost builder" /etc/hosts
sed -i "/preserve_hostname/c preserve_hostname: true" /etc/cloud/cloud.cfg

mv /infra /home/ubuntu/infra
chown -R ubuntu:ubuntu /home/ubuntu/infra
sudo -u ubuntu make -C /home/ubuntu/infra ce

ln -s /efs/squash-images /opt/squash-images
