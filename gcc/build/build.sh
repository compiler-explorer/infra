#!/bin/bash

set -e

ROOT=$(pwd)
VERSION=$1
if echo ${VERSION} | grep 'trunk'; then
    VERSION=trunk-$(date +%Y%m%d)
    URL=svn://gcc.gnu.org/svn/gcc/trunk 
    MAJOR=8
    MAJOR_MINOR=8-trunk
elif echo ${VERSION} | grep 'snapshot-'; then
    VERSION=${VERSION/#snapshot-/}
    TARBALL=gcc-${VERSION}.tar.xz
    URL=ftp://gcc.gnu.org/pub/gcc/snapshots/${VERSION}/${TARBALL}
    MAJOR=$(echo ${VERSION} | grep -oE '^[0-9]+')
    MAJOR_MINOR=${MAJOR}-snapshot
else
    MAJOR=$(echo ${VERSION} | grep -oE '^[0-9]+')
    MAJOR_MINOR=$(echo ${VERSION} | grep -oE '^[0-9]+\.[0-9]+')
    TARBALL=gcc-${VERSION}.tar.bz2
    if [[ "${MAJOR}" -gt 7 ]]; then TARBALL=gcc-${VERSION}.tar.xz; fi
    if [[ "${MAJOR_MINOR}" = "7.2" ]]; then TARBALL=gcc-${VERSION}.tar.xz; fi
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
    svn checkout ${URL} gcc-${VERSION}
else
    if [[ ! -e ${TARBALL} ]]; then
        echo "Fetching GCC"
        curl -L -O ${URL}
    fi
    rm -rf gcc-${VERSION}
    echo "Extracting GCC..."
    tar axf ${TARBALL}
fi

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
CONFIG+=" --host=x86_64-linux-gnu"
CONFIG+=" --target=x86_64-linux-gnu"
CONFIG+=" --disable-multilib"
CONFIG+=" --disable-bootstrap"
CONFIG+=" --disable-multiarch"
CONFIG+=" --with-arch-32=i586"  # For go, apparently
CONFIG+=" --enable-clocale=gnu"
CONFIG+=" --enable-languages=c,c++,go,fortran"
CONFIG+=" --enable-ld=yes"
CONFIG+=" --enable-gold=yes"
CONFIG+=" --enable-libstdcxx-debug"
CONFIG+=" --enable-libstdcxx-time=yes"
CONFIG+=" --enable-linker-build-id" 
CONFIG+=" --enable-lto"
CONFIG+=" --enable-plugins"
CONFIG+=" --enable-threads=posix"
CONFIG+=" --with-pkgversion=GCC-Explorer-Build"
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
if [[ -f ./contrib/download_prerequisites ]]; then
    ./contrib/download_prerequisites
else
    # Older GCCs lacked it, so this is one stolen from GCC 4.6.1
    ../download_prerequisites
fi
popd

mkdir -p objdir
pushd objdir
../gcc-${VERSION}/configure --prefix ${STAGING_DIR} ${CONFIG}
make -j$(nproc)
make ${INSTALL_TARGET}
popd

if [[ ! -z "${BINUTILS_VERSION}" ]]; then
    # Work around insane in-tree built ld issue
    for bindir in ${STAGING_DIR}/{,x86_64-linux-gnu/}bin
    do
        pushd ${bindir}
        ln -s ld ld-new
        popd
    done
fi

# Compress all the images with upx
for EXE in $(find ${STAGING_DIR} -type f -executable -not -regex '.*\.so.*'); do
    upx ${EXE} || true
done

tar Jcf ${OUTPUT} --transform "s,^./,./gcc-${VERSION}/," -C ${STAGING_DIR} .

if [[ ! -z "${S3OUTPUT}" ]]; then
    s3cmd put --rr ${OUTPUT} ${S3OUTPUT}
fi
