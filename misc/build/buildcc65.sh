#!/bin/bash

set -ex

VERSION=$1
if echo ${VERSION} | grep 'trunk'; then
    VERSION=trunk-$(date +%Y%m%d)
    BRANCH=master
else
    BRANCH=V${VERSION}
fi

OUTPUT=/root/cc65-${VERSION}.tar.xz
S3OUTPUT=""
if echo $2 | grep s3://; then
    S3OUTPUT=$2
else
    OUTPUT=${2-/root/cc65-${VERSION}.tar.xz}
fi

PREFIX=$(pwd)/prefix
DIR=$(pwd)/cc65
git clone --depth 1 -b ${BRANCH} https://github.com/cc65/cc65.git ${DIR}

make -C ${DIR} -j$(nproc)
make -C ${DIR} PREFIX=${PREFIX} install

export XZ_DEFAULTS="-T 0"
tar Jcf ${OUTPUT} --transform "s,^./,./cc65-${VERSION}/," -C ${PREFIX} .

if [[ ! -z "${S3OUTPUT}" ]]; then
    s3cmd put --rr ${OUTPUT} ${S3OUTPUT}
fi
