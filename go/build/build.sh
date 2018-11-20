#!/bin/bash

set -ex

VERSION=$1
if echo ${VERSION} | grep 'trunk'; then
    VERSION=trunk-$(date +%Y%m%d)
    BRANCH=master
else
    BRANCH=go${VERSION}
fi

OUTPUT=/root/go-${VERSION}.tar.xz
S3OUTPUT=""
if echo $2 | grep s3://; then
    S3OUTPUT=$2
else
    OUTPUT=${2-/root/go-${VERSION}.tar.xz}
fi

DIR=${BRANCH}/go
git clone --depth 1 -b ${BRANCH} https://go.googlesource.com/go ${DIR}

pushd ${DIR}/src
./make.bash
popd

pushd ${DIR}
rm -rf \
    .git \
    .gitattributes \
    .github \
    pkg/bootstrap \
    pkg/linux_amd64/cmd \
    pkg/obj
popd

export XZ_DEFAULTS="-T 0"
tar Jcf ${OUTPUT} --transform "s,^./go,./go-${VERSION}/," -C ${BRANCH} .

if [[ ! -z "${S3OUTPUT}" ]]; then
    s3cmd put --rr ${OUTPUT} ${S3OUTPUT}
fi
