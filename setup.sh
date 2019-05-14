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

if [[ ! -f /updated.2 ]]; then
    dpkg --add-architecture i386
    apt-get -y update
    apt-get install -y \
        binutils-multiarch \
        bison \
        bzip2 \
        curl \
        file \
        flex \
        g++ \
        gawk \
        gcc \
        gnat \
        jq \
        libc6-dev-i386 \
        libdatetime-perl \
        libelf-dev \
        libwww-perl \
        linux-libc-dev \
        make \
        nfs-common \
        nginx \
        patch \
        python-pip \
        s3cmd \
        subversion \
        texinfo \
        unzip \
        wine64 \
        wget \
        xz-utils
    touch /updated.2
fi

cp nginx/nginx.conf /etc/nginx/nginx.conf
systemctl restart nginx

cp /compiler-explorer-image/init/compiler-explorer.service /lib/systemd/system/compiler-explorer.service
systemctl daemon-reload
systemctl enable compiler-explorer
