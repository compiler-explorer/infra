#!/bin/bash

set -exuo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

env EXTRA_NFS_ARGS=",ro" "${DIR}/setup-common.sh"

apt-get -y update
apt-get -y install software-properties-common
dpkg --add-architecture i386
curl -s https://dl.winehq.org/wine-builds/winehq.key | apt-key add -
# TODO at some point see if we can upgrade wine
apt-add-repository 'deb https://dl.winehq.org/wine-builds/ubuntu/ bionic main'
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
    libc6-dev-i386 \
    libdatetime-perl \
    libelf-dev \
    libgmp3-dev \
    libprotobuf-dev \
    libnl-route-3-dev \
    libwww-perl \
    linux-libc-dev \
    make \
    nfs-common \
    nginx \
    patch \
    pkg-config \
    protobuf-compiler \
    python3-pip \
    python3.8-venv \
    s3cmd \
    subversion \
    texinfo \
    unzip \
    wget \
    winehq-stable=4.0.3~bionic \
    wine-stable=4.0.3~bionic \
    wine-stable-amd64=4.0.3~bionic \
    wine-stable-i386=4.0.3~bionic \
    xz-utils

pushd /tmp
git clone https://github.com/apmorton/firejail.git
cd firejail
git checkout 0.9.58.2-ce-patch.1
./configure --enable-apparmor
make "-j$(nproc)"
make install
popd

pushd /tmp
git clone --recursive --branch 3.0 https://github.com/google/nsjail.git
cd nsjail
make "-j$(nproc)"
cp nsjail /usr/local/bin/nsjail
popd


pushd /opt
# node.js
TARGET_NODE_VERSION=v16.13.1
echo "Installing node ${TARGET_NODE_VERSION}"
curl -sL "https://nodejs.org/dist/${TARGET_NODE_VERSION}/node-${TARGET_NODE_VERSION}-linux-x64.tar.gz" | tar zxf - && mv node-${TARGET_NODE_VERSION}-linux-x64 node
popd

# nsolid
mkdir /tmp/nsolid
pushd /tmp/nsolid
NSOLID_VERSION=4.7.1
curl -sL https://s3-us-west-2.amazonaws.com/nodesource-public-downloads/4.7.1/artifacts/bundles/nsolid-bundle-v${NSOLID_VERSION}-linux-x64.tar.gz | tar zxf - --strip-components 2

mkdir /opt/nsolid
tar zxf nsolid-v${NSOLID_VERSION}-gallium-linux-x64.tar.gz --strip-components 1 -C /opt/nsolid
popd
rm -rf /tmp/nsolid

cp nginx/nginx.conf /etc/nginx/nginx.conf
systemctl restart nginx

cp /infra/init/compiler-explorer.service /lib/systemd/system/compiler-explorer.service
systemctl daemon-reload
systemctl enable compiler-explorer

adduser --system --group ce
