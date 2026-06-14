#!/bin/bash

set -exuo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Use common setup but skip NFS and CEFS (routers don't need filesystem mounts)
export SKIP_NFS_SETUP=1
export SKIP_CEFS_SETUP=1

# Use router-specific SSM parameters for Papertrail logging
export LOG_DEST_HOST_PARAM="/compiler-explorer/logDestHostRouter"
export LOG_DEST_PORT_PARAM="/compiler-explorer/logDestPortRouter"

"${DIR}/setup-common.sh"

apt-get -y update
apt-get -y install \
    curl \
    jq \
    nginx

# Install Node.js (arm64 build matches the Lambda runtime major)
pushd /opt
TARGET_NODE_VERSION="v$(cat "${DIR}/node-version")"
echo "Installing node ${TARGET_NODE_VERSION}"
curl -sL "https://nodejs.org/dist/${TARGET_NODE_VERSION}/node-${TARGET_NODE_VERSION}-linux-arm64.tar.xz" | tar xJf - && mv "node-${TARGET_NODE_VERSION}-linux-arm64" node
popd


# Configure nginx for health checks
cp /infra/nginx/ce-router.conf /etc/nginx/nginx.conf
systemctl restart nginx

# Install systemd service
cp /infra/init/ce-router.service /lib/systemd/system/ce-router.service
systemctl daemon-reload
systemctl enable ce-router

# Create ce user for running the router
adduser --system --group ce

# Don't set hostname here - let cloud-init handle it like other instances

# Configure CloudWatch logging
mkdir -p /var/log/ce-router
chown ce:ce /var/log/ce-router

# Configure AWS credentials location
mkdir -p /home/ce/.aws
echo -e "[default]\nregion=us-east-1" > /home/ce/.aws/config
chown -R ce:ce /home/ce/.aws

# Memory and network optimizations
mkdir -p /etc/sysctl.d
cat >/etc/sysctl.d/99-ce.conf <<EOF
vm.min_free_kbytes=65536
net.core.rmem_max=268435456
net.core.wmem_max=268435456
net.ipv4.tcp_rmem=4096 65536 268435456
net.ipv4.tcp_wmem=4096 65536 268435456
EOF
sysctl -p /etc/sysctl.d/99-ce.conf
