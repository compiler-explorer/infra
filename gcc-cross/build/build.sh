#!/bin/bash

set -e

ROOT=$(pwd)
CT=${ROOT}/crosstool-ng/ct-ng

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

cp ${ARCHITECTURE}-${VERSION}.config .config
${CT} oldconfig
${CT} build.$(nproc)

# Compress all the images with upx
for EXE in $(find ${STAGING_DIR} -type f -executable -not -regex '.*\.so.*'); do
    upx ${EXE} || true
done

tar Jcf ${OUTPUT} -C ${STAGING_DIR}/.. gcc-${VERSION}

if [[ ! -z "${S3OUTPUT}" ]]; then
    s3cmd put --rr ${OUTPUT} ${S3OUTPUT}
fi
