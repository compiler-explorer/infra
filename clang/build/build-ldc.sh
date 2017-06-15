#!/bin/bash

set -e

# Grab CE's GCC 6.3.0 for its binutils (which is what the site uses to link currently)
mkdir -p /opt/compiler-explorer
pushd /opt/compiler-explorer
curl -sL https://s3.amazonaws.com/compiler-explorer/opt/gcc-6.3.0.tar.xz | tar Jxf -
popd

ROOT=$(pwd)
VERSION=$1

OUTPUT=/root/ldc2-${VERSION}.tar.xz
S3OUTPUT=""
if echo $2 | grep s3://; then
    S3OUTPUT=$2
else
    OUTPUT=${2-/root/ldc2-${VERSION}.tar.xz}
fi

STAGING_DIR=$(pwd)/staging
rm -rf ${STAGING_DIR}
mkdir -p ${STAGING_DIR}

# Get LLVM source
LLVM_VERSION=4.0.0
mkdir llvm
cd llvm
wget -q http://releases.llvm.org/$LLVM_VERSION/llvm-$LLVM_VERSION.src.tar.xz
tar -xf llvm* --strip 1
cd ..

# Build LLVM
mkdir build
cd build
cmake -G "Unix Makefiles" ../llvm \
    -DCMAKE_BUILD_TYPE:STRING=Release \
    -DCMAKE_INSTALL_PREFIX:PATH=/root/staging \
    -DLLVM_BINUTILS_INCDIR:PATH=/opt/compiler-explorer/gcc-6.3.0/lib/gcc/x86_64-linux-gnu/6.3.0/plugin/include/
make -j$(nproc) install
cd ..

# Building LDC requires a D compiler, get prebuilt LDC 1.1.0
mkdir -p ldc110
cd ldc110
wget -q https://github.com/ldc-developers/ldc/releases/download/v1.1.0/ldc2-1.1.0-linux-x86_64.tar.xz
tar xf ldc2-1.1.0-linux-x86_64.tar.xz --strip 1
export DMD=$(pwd)/bin/ldmd2
cd ..

# Get LDC source
mkdir ldc
cd ldc
curl -sL https://github.com/ldc-developers/ldc/releases/download/v${VERSION}/ldc2-${VERSION}-src.tar.gz | tar zxf - --strip 1
cd ..

# Build LDC
mkdir buildldc
cd buildldc
cmake -G "Unix Makefiles" ../ldc \
    -DLLVM_ROOT_DIR=/root/staging \
    -DCMAKE_INSTALL_PREFIX:PATH=/root/staging
make -j$(nproc) install
cd ..

# Compress all the binaries with upx
upx -4 ${STAGING_DIR}/bin/* || true

tar Jcf ${OUTPUT} --transform "s,^./,./ldc2-${VERSION}/," -C ${STAGING_DIR} .

if [[ ! -z "${S3OUTPUT}" ]]; then
    s3cmd put --rr ${OUTPUT} ${S3OUTPUT}
fi
