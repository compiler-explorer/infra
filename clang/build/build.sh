#!/bin/bash

set -ex

# Grab CE's GCC for its binutils
BINUTILS_GCC_VERSION=9.2.0
mkdir -p /opt/compiler-explorer
pushd /opt/compiler-explorer
curl -sL https://s3.amazonaws.com/compiler-explorer/opt/gcc-${BINUTILS_GCC_VERSION}.tar.xz | tar Jxf -
popd

ROOT=$(pwd)
VERSION=$1
if echo ${VERSION} | grep 'trunk'; then
    TAG=trunk
    VERSION=trunk-$(date +%Y%m%d)
else
    SPLIT=(${VERSION//-/ })
    VERSION=${SPLIT[0]}
    VSN=$(echo ${VERSION} | sed 's/\.//g')
    TAG=tags/RELEASE_${VSN}/${SPLIT[1]-final}
fi

OUTPUT=/root/clang-${VERSION}.tar.xz
S3OUTPUT=""
if echo $2 | grep s3://; then
    S3OUTPUT=$2
else
    OUTPUT=${2-/root/clang-${VERSION}.tar.xz}
fi

STAGING_DIR=$(pwd)/staging
rm -rf ${STAGING_DIR}
mkdir -p ${STAGING_DIR}

# Setup llvm-project checkout
git clone --depth 1 https://github.com/llvm/llvm-project.git

# Setup build directory and build configuration
mkdir build
cd build
cmake -DLLVM_ENABLE_PROJECTS="clang;libcxx;libcxxabi;compiler-rt;lld;polly" -G "Unix Makefiles" ../llvm-project/llvm \
    -DCMAKE_BUILD_TYPE:STRING=Release \
    -DCMAKE_INSTALL_PREFIX:PATH=/root/staging \
    -DLLVM_BINUTILS_INCDIR:PATH=/opt/compiler-explorer/gcc-${BINUTILS_GCC_VERSION}/lib/gcc/x86_64-linux-gnu/${BINUTILS_GCC_VERSION}/plugin/include \
    -DLLVM_EXPERIMENTAL_TARGETS_TO_BUILD="RISCV;WebAssembly"

# Build and install artifacts
make -j$(nproc) install

# Don't try to compress the binaries as they don't like it

export XZ_DEFAULTS="-T 0"
tar Jcf ${OUTPUT} --transform "s,^./,./clang-${VERSION}/," -C ${STAGING_DIR} .

if [[ ! -z "${S3OUTPUT}" ]]; then
    s3cmd put --rr ${OUTPUT} ${S3OUTPUT}
fi
