#!/bin/bash

set -e

# Grab CE's GCC 7.3.0 for its binutils (which is what the site uses to link currently)
mkdir -p /opt/compiler-explorer
pushd /opt/compiler-explorer
curl -sL https://s3.amazonaws.com/compiler-explorer/opt/gcc-7.3.0.tar.xz | tar Jxf -
popd

ROOT=$(pwd)
TAG=trunk
VERSION=concepts-trunk-$(date +%Y%m%d)

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

git clone https://github.com/llvm-mirror/llvm.git
pushd llvm/tools
git clone https://github.com/saarraz/clang-concepts.git clang
popd
pushd llvm/projects
git clone https://github.com/llvm-mirror/libcxx.git
git clone https://github.com/llvm-mirror/libcxxabi.git
popd

mkdir build
cd build
cmake -G "Unix Makefiles" ../llvm \
    -DCMAKE_BUILD_TYPE:STRING=Release \
    -DCMAKE_INSTALL_PREFIX:PATH=/root/staging \
    -DLLVM_BINUTILS_INCDIR:PATH=/opt/compiler-explorer/gcc-7.3.0/lib/gcc/x86_64-linux-gnu/7.3.0/plugin/include/

make -j$(nproc) install

# Compress all the binaries with upx
upx -4 ${STAGING_DIR}/bin/* || true

tar Jcf ${OUTPUT} --transform "s,^./,./clang-${VERSION}/," -C ${STAGING_DIR} .

if [[ ! -z "${S3OUTPUT}" ]]; then
    s3cmd put --rr ${OUTPUT} ${S3OUTPUT}
fi
