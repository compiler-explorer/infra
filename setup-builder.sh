#!/bin/bash

set -ex

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

env EXTRA_NFS_ARGS="" "${DIR}/setup-common.sh"

wget -qO- https://get.docker.com/ | sh

apt -y install python2.7 mosh fish jq ssmtp cronic subversion upx gdb
chsh ubuntu -s /usr/bin/fish

cd /home/ubuntu/infra
pip install --upgrade -r requirements.txt

# Install private and public keys
aws ssm get-parameter --name /admin/ce_private_key | jq -r .Parameter.Value >/home/ubuntu/.ssh/id_rsa

chmod 600 /home/ubuntu/.ssh/id_rsa
aws s3 cp s3://compiler-explorer/authorized_keys/admin.key /home/ubuntu/.ssh/id_rsa.pub
chown -R ubuntu:ubuntu /home/ubuntu/.ssh
chown -R ubuntu:ubuntu /home/ubuntu/infra

sudo -u ubuntu fish setup.fish
crontab -u ubuntu crontab.builder

echo builder-node >/etc/hostname
hostname builder-node
sed -i "/127.0.0.1/c 127.0.0.1 localhost builder-node" /etc/hosts
