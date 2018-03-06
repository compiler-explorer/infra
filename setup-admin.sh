#!/bin/bash

set -ex

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

if [[ "$1" != "--updated" ]]; then
    sudo -u ubuntu git -C ${DIR} pull
    pwd
    exec bash ${BASH_SOURCE[0]} --updated
    exit 0
fi

EXTRA_NFS_ARGS=""
${DIR}/setup-common.sh

apt -y install python2.7 python-pip mosh fish jq
chsh ubuntu -s /usr/bin/fish

cd /home/ubuntu/compiler-explorer-image
pip install --upgrade pip awscli
pip install -r requirements.txt

# Install private and public keys
aws ssm get-parameter --name /admin/ce_private_key | jq -r .Parameter.Value > /home/ubuntu/.ssh/id_rsa
chmod 600 /home/ubuntu/.ssh/id_rsa
aws s3 cp s3://compiler-explorer/authorized_keys/admin.key /home/ubuntu/.ssh/id_rsa.pub
chown -R ubuntu:ubuntu /home/ubuntu/.ssh

sudo -u ubuntu fish setup.fish
