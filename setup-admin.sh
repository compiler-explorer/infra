#!/bin/bash

set -exuo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${DIR}"

if [[ "$1" != "--updated" ]]; then
  sudo -u ubuntu git -C "${DIR}" pull
  pwd
  exec bash "${BASH_SOURCE[0]}" --updated
  exit 0
fi

env EXTRA_NFS_ARGS="" INSTALL_TYPE="admin" "${DIR}/setup-common.sh"

apt -y install \
  autojump \
  cronic \
  fish \
  gdb \
  jq \
  libc6-dev-i386 \
  m4 \
  mosh \
  python3 \
  python3-venv \
  python3.8 \
  python3.8-venv \
  squashfs-tools-ng \
  subversion \
  upx \
  zlib1g-dev
chsh ubuntu -s /usr/bin/fish

cd /home/ubuntu/infra

# Setup the fish prompt
ln -sf admin/fish_prompt.fish ~/.config/fish/fish_prompt.fish

# Install private and public keys
aws ssm get-parameter --name /admin/ce_private_key | jq -r .Parameter.Value >/home/ubuntu/.ssh/id_rsa

chmod 600 /home/ubuntu/.ssh/id_rsa
aws s3 cp s3://compiler-explorer/authorized_keys/admin.key /home/ubuntu/.ssh/id_rsa.pub
mkdir /home/ubuntu/.ssh/controlmasters
cat > /home/ubuntu/.ssh/config <<EOF
Host *
  ControlMaster auto
  ControlPath ~/.ssh/controlmasters/%r@%h:%p
  ControlPersist 10
EOF
chown -R ubuntu:ubuntu /home/ubuntu/.ssh
chown -R ubuntu:ubuntu /home/ubuntu/infra

sudo -u ubuntu fish setup.fish
crontab -u ubuntu crontab.admin

echo admin-node >/etc/hostname
hostname admin-node
sed -i "/127.0.0.1/c 127.0.0.1 localhost admin-node" /etc/hosts
sed -i "/preserve_hostname/c preserve_hostname: true" /etc/cloud/cloud.cfg

if ! grep vm.min_free_kbytes /etc/sysctl.conf; then
  echo "vm.min_free_kbytes=65536" >>/etc/sysctl.conf
  sysctl -p
fi
