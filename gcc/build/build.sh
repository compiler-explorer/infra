#!/bin/bash

set -ex

ROOT=$(pwd)
VERSION=$1
LANGUAGES=c,c++,fortran,ada
if echo "${VERSION}" | grep 'embed-trunk'; then
    VERSION=embed-trunk-$(date +%Y%m%d)
    URL=https://github.com/ThePhD/gcc.git
    BRANCH=feature/embed
    MAJOR=10
    MAJOR_MINOR=10-trunk
    LANGUAGES=c,c++
elif echo "${VERSION}" | grep 'lock3-contracts-trunk'; then
    VERSION=lock3-contracts-trunk-$(date +%Y%m%d)
    URL=https://gitlab.com/lock3/gcc-new.git/
    BRANCH=contracts
    MAJOR=10
    MAJOR_MINOR=10-trunk
    LANGUAGES=c,c++
elif echo "${VERSION}" | grep 'cxx-modules-trunk'; then
    VERSION=cxx-modules-trunk-$(date +%Y%m%d)
    URL=svn://gcc.gnu.org/svn/gcc/branches/c++-modules
    MAJOR=10
    MAJOR_MINOR=10-trunk
    LANGUAGES=c,c++
elif echo "${VERSION}" | grep 'cxx-coroutines-trunk'; then
    VERSION=cxx-coroutines-trunk-$(date +%Y%m%d)
    URL=https://github.com/iains/gcc-cxx-coroutines
    MAJOR=10
    MAJOR_MINOR=10-trunk
    LANGUAGES=c,c++
elif echo "${VERSION}" | grep 'trunk'; then
    VERSION=trunk-$(date +%Y%m%d)
    URL=svn://gcc.gnu.org/svn/gcc/trunk
    MAJOR=10
    MAJOR_MINOR=10-trunk
    LANGUAGES=${LANGUAGES},d
elif echo "${VERSION}" | grep 'snapshot-'; then
    VERSION=${VERSION/#snapshot-/}
    TARBALL=gcc-${VERSION}.tar.xz
    URL=ftp://gcc.gnu.org/pub/gcc/snapshots/${VERSION}/${TARBALL}
    MAJOR=$(echo "${VERSION}" | grep -oE '^[0-9]+')
    MAJOR_MINOR=${MAJOR}-snapshot
    LANGUAGES=${LANGUAGES},d
else
    MAJOR=$(echo "${VERSION}" | grep -oE '^[0-9]+')
    MAJOR_MINOR=$(echo "${VERSION}" | grep -oE '^[0-9]+\.[0-9]+')
    TARBALL=gcc-${VERSION}.tar.bz2
    if [[ "${MAJOR}" -gt 8 ]]; then LANGUAGES=${LANGUAGES},d; fi
    if [[ "${MAJOR}" -gt 7 ]]; then TARBALL=gcc-${VERSION}.tar.xz; fi
    if [[ "${MAJOR_MINOR}" == "7.2" ]]; then TARBALL=gcc-${VERSION}.tar.xz; fi
    if [[ "${MAJOR_MINOR}" == "7.3" ]]; then TARBALL=gcc-${VERSION}.tar.xz; fi
    if [[ "${MAJOR_MINOR}" == "7.4" ]]; then TARBALL=gcc-${VERSION}.tar.xz; fi
    if [[ "${MAJOR_MINOR}" == "5.5" ]]; then TARBALL=gcc-${VERSION}.tar.xz; fi
    if [[ "${MAJOR_MINOR}" == "6.4" ]]; then TARBALL=gcc-${VERSION}.tar.xz; fi
    URL=ftp://ftp.gnu.org/gnu/gcc/gcc-${VERSION}/${TARBALL}
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
STAGING_DIR=$(pwd)/staging
INSTALL_TARGET=install-strip
rm -rf ${STAGING_DIR}
mkdir -p ${STAGING_DIR}

if echo ${URL} | grep svn://; then
    rm -rf gcc-${VERSION}
    svn checkout -q ${URL} gcc-${VERSION}
elif echo ${URL} | grep .git; then
    rm -rf gcc-${VERSION}
    git clone -q ${URL} gcc-${VERSION}
    pushd gcc-${VERSION}
    git checkout ${BRANCH}
    popd
else
    if [[ ! -e ${TARBALL} ]]; then
        echo "Fetching GCC" from ${URL}...
        curl -L -O ${URL}
    fi
    rm -rf gcc-${VERSION}
    echo "Extracting GCC..."
    tar axf ${TARBALL}
fi

echo "Downloading prerequisites"
pushd gcc-${VERSION}
if [[ -f ./contrib/download_prerequisites ]]; then
    ./contrib/download_prerequisites
else
    # Older GCCs lacked it, so this is one stolen from GCC 4.6.1
    ../download_prerequisites
fi
popd

applyPatchesAndConfig() {
    local PATCH_DIR=${ROOT}/patches/$1
    local PATCH=""
    if [[ -d ${PATCH_DIR} ]]; then
        echo "Applying patches from ${PATCH_DIR}"
        pushd gcc-${VERSION}
        for PATCH in ${PATCH_DIR}/*; do
            patch -p1 <${PATCH}
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
CONFIG+=" --host=x86_64-linux-gnu"
CONFIG+=" --target=x86_64-linux-gnu"
CONFIG+=" --disable-bootstrap"
CONFIG+=" --enable-multiarch"
CONFIG+=" --with-abi=m64"
CONFIG+=" --with-multilib-list=m32,m64,mx32"
CONFIG+=" --enable-multilib"
CONFIG+=" --enable-clocale=gnu"
CONFIG+=" --enable-languages=${LANGUAGES}"
CONFIG+=" --enable-ld=yes"
CONFIG+=" --enable-gold=yes"
CONFIG+=" --enable-libstdcxx-debug"
CONFIG+=" --enable-libstdcxx-time=yes"
CONFIG+=" --enable-linker-build-id"
CONFIG+=" --enable-lto"
CONFIG+=" --enable-plugins"
CONFIG+=" --enable-threads=posix"
CONFIG+=" --with-pkgversion=Compiler-Explorer-Build"
BINUTILS_VERSION=2.29.1

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
    mkdir ${BINUTILS_DIR}/objdir
    pushd ${BINUTILS_DIR}/objdir
    ../configure --prefix=${STAGING_DIR} ${CONFIG}
    make -j$(nproc)
    make ${INSTALL_TARGET}
    popd
fi

mkdir -p objdir
pushd objdir
../gcc-${VERSION}/configure --prefix=${STAGING_DIR} ${CONFIG}
make -j$(nproc)
make ${INSTALL_TARGET}
popd

export XZ_DEFAULTS="-T 0"
tar Jcf ${OUTPUT} --transform "s,^./,./gcc-${VERSION}/," -C ${STAGING_DIR} .

if [[ ! -z "${S3OUTPUT}" ]]; then
    s3cmd put --rr ${OUTPUT} ${S3OUTPUT}
fi
