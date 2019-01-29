#!/bin/bash

set -ex

ROOT=$(pwd)
VERSION=$1
if [[ "$VERSION" != "1.27" ]]; then
    echo "Wrong version"
    exit 1
fi

OUTPUT=/root/gcc-${VERSION}.tar.xz
S3OUTPUT=""
if echo $2 | grep s3://; then
    S3OUTPUT=$2
else
    OUTPUT=${2-/root/gcc-${VERSION}.tar.xz}
fi

# Workaround for Ubuntu builds
export LIBRARY_PATH=/usr/lib/x86_64-linux-gnu
STAGING_DIR=/opt/compiler-explorer/gcc-${VERSION}

MAJOR=1
MAJOR_MINOR=1.27

URL=https://gcc.gnu.org/pub/gcc/old-releases/gcc-${MAJOR}/gcc-${MAJOR_MINOR}.tar.bz2

curl -L ${URL} | tar jxf -

applyPatchesAndConfig() {
    local PATCH_DIR=${ROOT}/patches/$1
    local PATCH=""
    if [[ -d ${PATCH_DIR} ]]; then
        echo "Applying patches from ${PATCH_DIR}"
        pushd gcc-${VERSION}
        for PATCH in ${PATCH_DIR}/*; do
            echo "...${PATCH}"
            patch -p1 < ${PATCH}
        done
        popd
    fi

    local CONFIG_DIR=${ROOT}/config/$1
    local CONFIG_FILE=""
    if [[ -d ${CONFIG_DIR} ]]; then
        echo "Applying config from ${CONFIG_DIR}"
        for CONFIG_FILE in ${CONFIG_DIR}/*; do
            echo "...${CONFIG_FILE}"
            . ${CONFIG_FILE}
        done
    fi
}

applyPatchesAndConfig gcc${MAJOR}
applyPatchesAndConfig gcc${MAJOR_MINOR}

pushd gcc-${MAJOR_MINOR}
ln -s config-i386v.h config.h
ln -s tm-i386v.h tm.h
ln -s i386.md md
ln -s output-i386.c aux-output.c
sed -i "s|^bindir =.*|bindir = /opt/compiler-explorer/gcc-${VERSION}/bin|g" Makefile
sed -i "s|^libdir =.*|libdir = /opt/compiler-explorer/gcc-${VERSION}/lib|g" Makefile

make -j$(nproc)
make -j$(nproc) stage1
make -j$(nproc) CC=stage1/gcc CFLAGS="-O -Bstage1/ -Iinclude"
make -j$(nproc) install
popd

export XZ_DEFAULTS="-T 0"
tar Jcf ${OUTPUT} --transform "s,^./,./gcc-${VERSION}/," -C ${STAGING_DIR} .

if [[ ! -z "${S3OUTPUT}" ]]; then
    s3cmd put --rr ${OUTPUT} ${S3OUTPUT}
fi
