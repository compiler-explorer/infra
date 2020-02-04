#!/bin/bash

set -ex

ROOT=$(pwd)
VERSION=$1
if echo ${VERSION} | grep 'trunk'; then
    TAG=master
    VERSION=trunk-$(date +%Y%m%d)
else
    TAG=llvmorg-${VERSION}
fi

OUTPUT=/root/llvm-${VERSION}.tar.xz
S3OUTPUT=""
if echo $2 | grep s3://; then
    S3OUTPUT=$2
else
    OUTPUT=${2-/root/llvm-${VERSION}.tar.xz}
fi

STAGING_DIR=$(pwd)/staging
rm -rf ${STAGING_DIR}
mkdir -p ${STAGING_DIR}

# Setup llvm-project checkout
git clone --depth 1 --single-branch -b "${TAG}" https://github.com/llvm/llvm-project.git

# Setup build directory and build configuration
mkdir build
cd build
cmake -G "Unix Makefiles" ../llvm-project/llvm \
    -DCMAKE_INSTALL_PREFIX:PATH=/root/staging

# Build and install artifacts
make -j$(nproc) install-llvm-headers

export XZ_DEFAULTS="-T 0"
tar Jcf ${OUTPUT} --transform "s,^./,./llvm-${VERSION}/," -C ${STAGING_DIR} .

if [[ ! -z "${S3OUTPUT}" ]]; then
    s3cmd put --rr ${OUTPUT} ${S3OUTPUT}
fi
