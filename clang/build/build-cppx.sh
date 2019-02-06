#!/bin/bash

set -e

# Grab CE's GCC 8.2.0 for its binutils
mkdir -p /opt/compiler-explorer
pushd /opt/compiler-explorer
curl -sL https://s3.amazonaws.com/compiler-explorer/opt/gcc-8.2.0.tar.xz | tar Jxf -
popd

ROOT=$(pwd)
TAG=trunk
VERSION=cppx-trunk-$(date +%Y%m%d)

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

# Setup llvm root directory
git clone --single-branch https://github.com/llvm-mirror/llvm.git

# Checkout & configure clang
pushd llvm/tools
git clone --depth 1 --single-branch -b feature/metaprogramming https://gitlab.com/lock3/clang.git

# Load llvm revisions for this compiler build
pushd clang
source compiler-explorer-llvm-commits.sh
popd

popd

# Adjust llvm revision to match the cppx compiler's specified revision
(cd llvm && git reset --hard ${CE_LLVM_COMMIT})

# Checkout and configure libcxx
pushd llvm/projects
git clone --single-branch https://github.com/llvm-mirror/libcxx.git
(cd libcxx && git reset --hard ${CE_LIBCXX_COMMIT})
# Hack for new glibc not containing xlocale.h
perl -pi -e 's/defined\(__GLIBC__\) \|\| defined\(__APPLE__\)/defined(__APPLE__)/' libcxx/include/__locale
git clone --single-branch https://github.com/llvm-mirror/libcxxabi.git
(cd libcxxabi && git reset --hard ${CE_LIBCXXABI_COMMIT})
popd

mkdir build
cd build
cmake -G "Unix Makefiles" ../llvm \
    -DCMAKE_BUILD_TYPE:STRING=Release \
    -DCMAKE_INSTALL_PREFIX:PATH=/root/staging \
    -DLLVM_BINUTILS_INCDIR:PATH=/opt/compiler-explorer/gcc-8.2.0/lib/gcc/x86_64-linux-gnu/8.2.0/plugin/include/

make -j$(nproc) install

export XZ_DEFAULTS="-T 0"
tar Jcf ${OUTPUT} --transform "s,^./,./clang-${VERSION}/," -C ${STAGING_DIR} .

if [[ ! -z "${S3OUTPUT}" ]]; then
    s3cmd put --rr ${OUTPUT} ${S3OUTPUT}
fi
