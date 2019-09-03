#!/bin/bash

set -ex

ENV=$(curl -sf http://169.254.169.254/latest/user-data | tr A-Z a-z || true)
ENV=${ENV:-prod}
BRANCH=master
if [[ "$ENV" = "beta" ]]; then
BRANCH=beta
fi
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

if [[ "$1" != "--updated" || "$2" != "${BRANCH}" ]]; then
    git --work-tree ${DIR} checkout ${BRANCH}
    git --work-tree ${DIR} pull
    exec bash ${BASH_SOURCE[0]} --updated ${BRANCH}
    exit 0
fi

env EXTRA_NFS_ARGS=",ro" ${DIR}/setup-common.sh

# Work around the fact that we need a writeable /opt/wine-stable, whereas /opt lives on EFS.
# DISABLED due to it causing issues with systemd isolated services (DNS, time etc), which fail with EINVAL during NAMESPACE.
# After much pain we discovered this was a bind mount in /opt causing issues. Not sure why it started happening..
#if ! grep "/opt/wine-stable" /etc/fstab; then
#    mkdir -p /var/opt/wine-stable
#    echo "/var/opt/wine-stable /opt/wine-stable none bind,defaults,x-systemd.requires=/opt,_netdev 0 0" >> /etc/fstab
#    mount -a
#fi

if [[ ! -f /updated.2 ]]; then
    dpkg --add-architecture i386
    curl -s https://dl.winehq.org/wine-builds/winehq.key | apt-key add -
    apt-add-repository 'deb https://dl.winehq.org/wine-builds/ubuntu/ bionic main'
    apt-get -y update
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
        libprotobuf-dev \
        libwww-perl \
        linux-libc-dev \
        make \
        nfs-common \
        nginx \
        patch \
        pkg-config \
        protobuf-compiler \
        python-pip \
        s3cmd \
        subversion \
        texinfo \
        unzip \
        wget \
        winehq-stable \
        xz-utils

    pushd /tmp
    git clone https://github.com/apmorton/firejail.git
    cd firejail
    git checkout 0.9.58.2-ce-patch.1
    ./configure --enable-apparmor
    make -j$(nproc)
    make install
    popd

    pushd /tmp
    git clone --recursive --branch 2.8 https://github.com/google/nsjail.git
    cd nsjail
    make -j$(nproc)
    cp nsjail /usr/local/bin/nsjail
    popd

    touch /updated.2
fi

cp nginx/nginx.conf /etc/nginx/nginx.conf
systemctl restart nginx

cp /compiler-explorer-image/init/compiler-explorer.service /lib/systemd/system/compiler-explorer.service
systemctl daemon-reload
systemctl enable compiler-explorer

if [[ -f /opt/compiler-explorer/libs/boost.tar.xz ]]; then
    mkdir -p /celibs
    tar xf /opt/compiler-explorer/libs/boost.tar.xz -C /celibs
fi
