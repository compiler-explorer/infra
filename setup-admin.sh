#!/bin/bash

set -ex

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd ${DIR}

if [[ "$1" != "--updated" ]]; then
    sudo -u ubuntu git -C ${DIR} pull
    pwd
    exec bash ${BASH_SOURCE[0]} --updated
    exit 0
fi

env EXTRA_NFS_ARGS="" ${DIR}/setup-common.sh

apt -y install python2.7 python-pip mosh fish jq ssmtp cronic subversion upx gdb autojump zlib1g-dev m4 python3 python3-venv python3-pip python3.8 python3.8-venv libc6-dev-i386
chsh ubuntu -s /usr/bin/fish

cd /home/ubuntu/infra
pip3 install --upgrade pip
hash -r pip3
pip3 install --upgrade awscli

# Setup the fish prompt
ln -sf admin/fish_prompt.fish ~/.config/fish/fish_prompt.fish

# Install private and public keys
aws ssm get-parameter --name /admin/ce_private_key | jq -r .Parameter.Value >/home/ubuntu/.ssh/id_rsa

chmod 600 /home/ubuntu/.ssh/id_rsa
aws s3 cp s3://compiler-explorer/authorized_keys/admin.key /home/ubuntu/.ssh/id_rsa.pub
chown -R ubuntu:ubuntu /home/ubuntu/.ssh
chown -R ubuntu:ubuntu /home/ubuntu/infra

sudo -u ubuntu fish setup.fish
crontab -u ubuntu crontab.admin

# Configure email
SMTP_PASS=$(aws ssm get-parameter --name /admin/smtp_pass | jq -r .Parameter.Value)
cat >/etc/ssmtp/ssmtp.conf <<EOF
root=postmaster
mailhub=email-smtp.us-east-1.amazonaws.com
hostname=compiler-explorer.com
FromLineOverride=NO
AuthUser=AKIAJZWPG4D3SSK45LJA
AuthPass=${SMTP_PASS}
UseTLS=YES
UseSTARTTLS=YES
EOF
cat >/etc/ssmtp/revaliases <<EOF
ubuntu:admin@compiler-explorer.com:email-smtp.us-east-1.amazonaws.com
EOF

chfn -f 'Compiler Explorer Admin' ubuntu
chmod 640 /etc/ssmtp/*

hostname admin-node
perl -pi -e 's/127.0.0.1 localhost/127.0.0.1 localhost admin-node/' /etc/hosts
