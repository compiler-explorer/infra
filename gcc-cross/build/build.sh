#!/bin/bash

set -e

ROOT=$(pwd)

ARCHITECTURE=$1
VERSION=$2
OUTPUT=/home/gcc-user/${ARCHITECTURE}-gcc-${VERSION}.tar.xz
STAGING_DIR=/opt/compiler-explorer/${ARCHITECTURE}/gcc-${VERSION}
export CT_PREFIX=${STAGING_DIR}

S3OUTPUT=""
if echo $3 | grep s3://; then
    S3OUTPUT=$3
else
    OUTPUT=${3-/home/gcc-user/${ARCHITECTURE}-gcc-${VERSION}.tar.xz}
fi

CONFIG_FILE=${ARCHITECTURE}-${VERSION}.config
if [[ -f old/${CONFIG_FILE} ]]; then
    CONFIG_FILE=old/${CONFIG_FILE}
    CT=${ROOT}/crosstool-ng/ct-ng
else
    CONFIG_FILE=new/${CONFIG_FILE}
    CT=${ROOT}/crosstool-ng-1.23.0/ct-ng
fi
cp ${CONFIG_FILE} .config
${CT} oldconfig
${CT} build.$(nproc)

tar Jcf ${OUTPUT} -C ${STAGING_DIR}/.. gcc-${VERSION}

if [[ ! -z "${S3OUTPUT}" ]]; then
    s3cmd put --rr ${OUTPUT} ${S3OUTPUT}
fi
