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
    libnginx-mod-http-brotli-filter \
    libnl-route-3-dev \
    libpciaccess0 \
    libprotobuf-dev \
    libwww-perl \
    linux-libc-dev \
    locales \
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

# Install user-requested locales
cat >> /etc/locale.gen << EOF
cs_CZ.UTF-8 UTF-8
cs_CZ ISO-8859-2
en_GB ISO-8859-1
de_DE.UTF-8 UTF-8
en_GB.UTF-8 UTF-8
en_US.UTF-8 UTF-8
en_US ISO-8859-1
en_US.ISO-8859-15 ISO-8859-15
is_IS.UTF-8 UTF-8
ja_JP.UTF-8 UTF-8
ja_JP.EUC-JP EUC-JP
ja_JP.SHIFT_JIS SHIFT_JIS
lt_LT.UTF-8 UTF-8
lt_LT ISO-8859-13
ru_RU.UTF-8 UTF-8
sv_SE.UTF-8 UTF-8
th_TH.UTF-8 UTF-8
th_TH TIS-620
zh_CN.UTF-8 UTF-8
zh_CN.GB18030 GB18030
zh_CN.GBK GBK
zh_CN GB2312
zh_HK.UTF-8 UTF-8
zh_HK BIG5-HKSCS
zh_TW.UTF-8 UTF-8
zh_TW.EUC-TW EUC-TW
zh_TW BIG5
EOF
locale-gen

# Workaround for older Clang versions (3.5-4.0) that expect xlocale.h,
# which was removed in newer glibc (folded into locale.h).
# See https://github.com/compiler-explorer/compiler-explorer/issues/7515
ln -sf /usr/include/locale.h /usr/include/xlocale.h

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
TARGET_NODE_VERSION="v$(cat "${DIR}/node-version")"
echo "Installing node ${TARGET_NODE_VERSION}"
curl -sL "https://nodejs.org/dist/${TARGET_NODE_VERSION}/node-${TARGET_NODE_VERSION}-linux-x64.tar.xz" | tar xJf - && mv "node-${TARGET_NODE_VERSION}-linux-x64" node
popd

cp nginx/nginx.conf /etc/nginx/nginx.conf
systemctl restart nginx

cp /infra/init/compiler-explorer.service /lib/systemd/system/compiler-explorer.service
systemctl daemon-reload
systemctl enable compiler-explorer

adduser --system --group ce
