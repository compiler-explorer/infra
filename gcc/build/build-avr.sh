#!/bin/bash

set -ex

VER_BINUTILS=2.32
VER_LIBC=2.0.0
VER_GCC=9.2.0

ROOT=$(pwd)
OUTPUT=/root/avr-gcc-${VER_GCC}.tar.xz
S3OUTPUT=""
if echo $2 | grep s3://; then
    S3OUTPUT=$2
else
    OUTPUT=${2-/root/avr-gcc-${VER_GCC}.tar.xz}
fi

# Workaround for Ubuntu builds
export LIBRARY_PATH=/usr/lib/x86_64-linux-gnu
STAGING_DIR=$(pwd)/staging
INSTALL_TARGET=install-strip
rm -rf ${STAGING_DIR}
mkdir -p ${STAGING_DIR}

CONFIG=""
CONFIG+=" --build=x86_64-linux-gnu"
CONFIG+=" --host=x86_64-linux-gnu"
CONFIG+=" --target=avr"
CONFIG+=" --disable-bootstrap"
CONFIG+=" --enable-clocale=gnu"
CONFIG+=" --enable-languages=c,c++"
CONFIG+=" --enable-ld=yes"
CONFIG+=" --enable-gold=yes"
CONFIG+=" --enable-linker-build-id"
CONFIG+=" --enable-lto"
CONFIG+=" --enable-plugins"
CONFIG+=" --with-pkgversion=Compiler-Explorer-Build"

echo "Will configure with ${CONFIG}"

# Binutils
BINUTILS_DIR=binutils-${VER_BINUTILS}
curl -L -O https://ftpmirror.gnu.org/binutils/${BINUTILS_DIR}.tar.gz
tar xfz ${BINUTILS_DIR}.tar.gz

mkdir ${BINUTILS_DIR}/objdir
pushd ${BINUTILS_DIR}/objdir
../configure --prefix=${STAGING_DIR} ${CONFIG}
make -j$(nproc)
make ${INSTALL_TARGET}
popd

# GCC
GCC_DIR=gcc-${VER_GCC}
curl -L -O https://ftp.gnu.org/gnu/gcc/gcc-${VER_GCC}/${GCC_DIR}.tar.gz
tar xfz ${GCC_DIR}.tar.gz
pushd ${GCC_DIR}
./contrib/download_prerequisites
popd

mkdir -p ${GCC_DIR}/objdir
pushd ${GCC_DIR}/objdir
../configure --prefix=${STAGING_DIR} ${CONFIG}
make -j$(nproc)
make ${INSTALL_TARGET}
popd

# LIBC
LIBC_DIR=avr-libc-${VER_LIBC}
curl -L -O http://download.savannah.gnu.org/releases/avr-libc/${LIBC_DIR}.tar.bz2
tar xfj ${LIBC_DIR}.tar.bz2

mkdir -p ${LIBC_DIR}/objdir
pushd ${LIBC_DIR}/objdir 
export PATH=${STAGING_DIR}/bin:$PATH
../configure --prefix=${STAGING_DIR} --build=`../config.guess` --host=avr
make -j$(nproc)
make ${INSTALL_TARGET}
popd


export XZ_DEFAULTS="-T 0"
tar Jcf ${OUTPUT} --transform "s,^./,./avr-gcc-${VER_GCC}/," -C ${STAGING_DIR} .

if [[ ! -z "${S3OUTPUT}" ]]; then
    s3cmd put --rr ${OUTPUT} ${S3OUTPUT}
fi
