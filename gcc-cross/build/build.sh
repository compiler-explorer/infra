#!/bin/bash

set -exuo pipefail

ROOT=$(pwd)

ARCHITECTURE=$1
VERSION=$2
OUTPUT=/home/gcc-user/${ARCHITECTURE}-gcc-${VERSION}.tar.xz
STAGING_DIR=/opt/compiler-explorer/${ARCHITECTURE}/gcc-${VERSION}
export CT_PREFIX=${STAGING_DIR}

ARG3=${3:-}
if [[ $ARG3 =~ s3:// ]]; then
    S3OUTPUT=$ARG3
else
    S3OUTPUT=""
    OUTPUT=${3-/home/gcc-user/${ARCHITECTURE}-gcc-${VERSION}.tar.xz}
fi

CONFIG_FILE=${ARCHITECTURE}-${VERSION}.config
for version in latest 1.24.0 1.23.0 1.22.0; do
    if [[ -f ${version}/${CONFIG_FILE} ]]; then
        CONFIG_FILE=${version}/${CONFIG_FILE}
        CT=${ROOT}/crosstool-ng-$version/ct-ng
        if [[ ! -x ${CT} ]]; then
            # installed version rather than ct-ng configured with --enable-local
            CT=${ROOT}/crosstool-ng-$version/bin/ct-ng
            if [[ ! -x ${CT} ]]; then
                echo "ct-ng $CT is either not found or not executable, also checked ${ROOT}/crosstool-ng-$version/ct-ng"
                exit 1
            fi
        fi
        break
    fi
done

cp ${CONFIG_FILE} .config
${CT} oldconfig
${CT} build.$(nproc)

export XZ_DEFAULTS="-T 0"
tar Jcf ${OUTPUT} -C ${STAGING_DIR}/.. gcc-${VERSION}

if [[ ! -z "${S3OUTPUT}" ]]; then
    s3cmd put --rr ${OUTPUT} ${S3OUTPUT}
fi
