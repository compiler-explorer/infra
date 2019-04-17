#!/bin/bash

set -ex

ROOT=$(pwd)
VERSION=$1
MAJOR=$(echo ${VERSION} | grep -oE '^[0-9]+')
MAJOR_MINOR=$(echo ${VERSION} | grep -oE '^[0-9]+\.[0-9]+')
URL=https://github.com/MaxKellermann/gcc.git
BRANCH=ce-${VERSION}

OUTPUT=/root/gcc-ce-${VERSION}.tar.xz
S3OUTPUT=""
if echo $2 | grep s3://; then
    S3OUTPUT=$2
else
    OUTPUT=${2-/root/gcc-${VERSION}.tar.xz}
fi

# Workaround for Ubuntu builds
export LIBRARY_PATH=/usr/lib/x86_64-linux-gnu
STAGING_DIR=$(pwd)/staging
BUILD_DIR=$(pwd)/build
SOURCE_DIR=$(pwd)/source
rm -rf ${STAGING_DIR} ${BUILD_DIR} ${SOURCE_DIR}
mkdir -p ${STAGING_DIR} ${BUILD_DIR} ${SOURCE_DIR}

# Checkout gcc
cd ${SOURCE_DIR}
git clone -q --branch ${BRANCH} --depth 1 ${URL} gcc
pushd gcc
./contrib/download_prerequisites
popd

git clone -q --depth 1 https://github.com/MaxKellermann/w32api.git
git clone -q --depth 1 https://github.com/MaxKellermann/mingwrt.git mingw
git clone -q --branch ce-2.31.1 --depth 1 https://github.com/MaxKellermann/binutils-gdb.git binutils
cp ${ROOT}/cegcc-build.sh ${SOURCE_DIR}/build.sh

cd ${BUILD_DIR}
bash ${SOURCE_DIR}/build.sh --prefix=${STAGING_DIR} -j $(nproc)

export XZ_DEFAULTS="-T 0"
tar Jcf ${OUTPUT} --transform "s,^./,./gcc-ce-${VERSION}/," -C ${STAGING_DIR} .

if [[ ! -z "${S3OUTPUT}" ]]; then
    s3cmd put --rr ${OUTPUT} ${S3OUTPUT}
fi
