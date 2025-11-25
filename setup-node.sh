#!/bin/bash

set -exuo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

env EXTRA_NFS_ARGS=",ro" "${DIR}/setup-common.sh"

apt-get -y update
apt-get -y install software-properties-common
dpkg --add-architecture i386
add-apt-repository ppa:deadsnakes/ppa
apt-get install -y \
    binutils-multiarch \
    bison \
    bzip2 \
    cgroup-tools \
    curl \
    dos2unix \
    file \
    flex \
    g++ \
    gawk \
    gcc \
    gnat \
    jq \
    libapparmor-dev \
    libc6-dev:i386 \
    libc6-dev-i386 \
    libdatetime-perl \
    libelf-dev \
    libffi-dev \
    libgmp3-dev \
    libnl-route-3-dev \
    libpciaccess0 \
    libprotobuf-dev \
    libwww-perl \
    linux-libc-dev \
    make \
    nfs-common \
    nginx \
    patch \
    pkg-config \
    protobuf-compiler \
    python-is-python3 \
    python3-pip \
    python3-venv \
    python3.8 \
    s3cmd \
    subversion \
    texinfo \
    unzip \
    wget \
    xz-utils

pushd /tmp
git clone --recursive --branch ce https://github.com/compiler-explorer/nsjail.git
cd nsjail
make "-j$(nproc)"
cp nsjail /usr/local/bin/nsjail
# Ubuntu 24.04+ needs AppArmor configuration to run unprivileged
. /etc/os-release
if [[ "$ID" == "ubuntu" ]] && [[ "${VERSION_ID%%.*}" -ge 24 ]]; then
    cat > /etc/apparmor.d/usr.local.bin.nsjail <<EOF
#include <tunables/global>

/usr/local/bin/nsjail flags=(unconfined) {
userns,
}
EOF
    apparmor_parser -r /etc/apparmor.d/usr.local.bin.nsjail
fi
popd


pushd /opt
# node.js
TARGET_NODE_VERSION=v22.13.1
echo "Installing node ${TARGET_NODE_VERSION}"
curl -sL "https://nodejs.org/dist/${TARGET_NODE_VERSION}/node-${TARGET_NODE_VERSION}-linux-x64.tar.xz" | tar xJf - && mv node-${TARGET_NODE_VERSION}-linux-x64 node
popd

cp nginx/nginx.conf /etc/nginx/nginx.conf
systemctl restart nginx

cp /infra/init/compiler-explorer.service /lib/systemd/system/compiler-explorer.service
systemctl daemon-reload
systemctl enable compiler-explorer

adduser --system --group ce
