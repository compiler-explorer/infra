#!/bin/bash

set -e

ROOT=$(pwd)
VERSION=$1
MAJOR=$(echo ${VERSION} | grep -oE '^[0-9]+')
MAJOR_MINOR=$(echo ${VERSION} | grep -oE '^[0-9]+\.[0-9]+')
OUTPUT=/root/gcc-${VERSION}.tar.xz
S3OUTPUT=""
if echo $2 | grep s3://; then
    S3OUTPUT=$2
else
    OUTPUT=${2-/root/gcc-${VERSION}.tar.xz}
fi

# Workaround for Ubuntu builds
export LIBRARY_PATH=/usr/lib/x86_64-linux-gnu
STAGING_DIR=$(pwd)/staging
rm -rf ${STAGING_DIR}
mkdir -p ${STAGING_DIR}

if [[ ! -e gcc-${VERSION}.tar.bz2 ]]; then
    echo "Fetching GCC"
    if echo ${VERSION} | grep 'snapshot-'; then
        VERSION=${VERSION/#snapshot-/}
        curl -L -O ftp://gcc.gnu.org/pub/gcc/snapshots/${VERSION}/gcc-${VERSION}.tar.bz2
    else
        curl -L -O ftp://ftp.gnu.org/gnu/gcc/gcc-${VERSION}/gcc-${VERSION}.tar.bz2
    fi
fi
rm -rf gcc-${VERSION}
echo "Extracting GCC..."
tar jxf gcc-${VERSION}.tar.bz2

applyPatchesAndConfig() {
    local PATCH_DIR=${ROOT}/patches/$1
    local PATCH=""
    if [[ -d ${PATCH_DIR} ]]; then
        echo "Applying patches from ${PATCH_DIR}"
        pushd gcc-${VERSION}
        for PATCH in ${PATCH_DIR}/*; do
            patch -p1 < ${PATCH}
        done
        popd
    fi

    local CONFIG_DIR=${ROOT}/config/$1
    local CONFIG_FILE=""
    if [[ -d ${CONFIG_DIR} ]]; then
        echo "Applying config from ${CONFIG_DIR}"
        for CONFIG_FILE in ${CONFIG_DIR}/*; do
            . ${CONFIG_FILE}
        done
    fi
}

CONFIG=""
CONFIG+=" --build=x86_64-linux-gnu"
CONFIG+=" --disable-multilibs"
CONFIG+=" --enable-clocale=gnu"
CONFIG+=" --enable-languages=c,c++"
CONFIG+=" --enable-ld=yes"
CONFIG+=" --enable-gold=yes"
CONFIG+=" --enable-libstdcxx-debug"
CONFIG+=" --enable-libstdcxx-time=yes"
CONFIG+=" --enable-linker-build-id" 
CONFIG+=" --enable-lto"
CONFIG+=" --enable-plugins"
CONFIG+=" --enable-threads=posix"
CONFIG+=" --host=x86_64-linux-gnu"
CONFIG+=" --target=x86_64-linux-gnu"
CONFIG+=" --with-pkgversion=GCC-Explorer-Build"
BINUTILS_VERSION=2.27

applyPatchesAndConfig gcc${MAJOR}
applyPatchesAndConfig gcc${MAJOR_MINOR}
applyPatchesAndConfig gcc${VERSION}

echo "Will configure with ${CONFIG}"

if [[ -z "${BINUTILS_VERSION}" ]]; then
    echo "Using host binutils $(ld -v)"
else
    echo "Fetching binutils ${BINUTILS_VERSION}"
    if [[ ! -e binutils-${BINUTILS_VERSION}.tar.bz2 ]]; then
        curl -L -O http://ftp.gnu.org/gnu/binutils/binutils-${BINUTILS_VERSION}.tar.bz2
    fi
    BINUTILS_DIR=binutils-${BINUTILS_VERSION}
    rm -rf ${BINUTILS_DIR}
    tar jxf binutils-${BINUTILS_VERSION}.tar.bz2
    BINUTILS_FILES=$(cd ${BINUTILS_DIR}; ls -1)
    pushd gcc-${VERSION}
    for file in ${BINUTILS_FILES}
    do
        if [ ! -e "$file" ]
        then
            ln -sf "../${BINUTILS_DIR}/${file}"
        fi
    done
    popd
fi

echo "Downloading prerequisites"
pushd gcc-${VERSION}
./contrib/download_prerequisites
popd

mkdir -p objdir
pushd objdir
../gcc-${VERSION}/configure --prefix ${STAGING_DIR} ${CONFIG}
make -j$(nproc)
make install-strip
popd

if [[ -z "${BINUTILS_VERSION}" ]]; then
    # Work around insane in-tree built ld issue
    for bindir in ${STAGING_DIR}/{,x86_64-linux-gnu/}bin
    do
        pushd ${bindir}
        ln -s ld ld-new
        popd
    done
fi

# Compress all the images with upx
upx --best ${STAGING_DIR}/bin/* || true
for EXE in cc1 cc1plus collect2 lto1 lto-wrapper; do
    upx --best ${STAGING_DIR}/libexec/gcc/x86_64-linux-gnu/${VERSION}/${EXE}
done

tar Jcf ${OUTPUT} --transform "s,^./,./gcc-${VERSION}/," -C ${STAGING_DIR} .

if [[ ! -z "${S3OUTPUT}" ]]; then
    s3cmd put --rr ${OUTPUT} ${S3OUTPUT}
fi
