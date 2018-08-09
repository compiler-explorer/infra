#!/bin/bash

set -ex

# Grab CE's GCC 7.2.0 for its binutils (which is what the site uses to link currently)
mkdir -p /opt/compiler-explorer
pushd /opt/compiler-explorer
curl -sL https://s3.amazonaws.com/compiler-explorer/opt/gcc-7.2.0.tar.xz | tar Jxf -
popd

ROOT=$(pwd)
VERSION=$1
LLVM_BASE=http://llvm.org/svn/llvm-project
if echo ${VERSION} | grep 'trunk'; then
    TAG=trunk
    VERSION=trunk-$(date +%Y%m%d)
    POLLY_BRANCH=master
else
    SPLIT=(${VERSION//-/ })
    VERSION=${SPLIT[0]}
    VSN=$(echo ${VERSION} | sed 's/\.//g')
    TAG=tags/RELEASE_${VSN}/${SPLIT[1]-final}
    POLLY_BRANCH=release_${VSN:0:2}
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

svn co -q ${LLVM_BASE}/llvm/${TAG} llvm
git clone -b ${POLLY_BRANCH} https://llvm.org/git/polly.git llvm/tools/polly
pushd llvm/tools
svn co -q ${LLVM_BASE}/cfe/${TAG} clang
popd
pushd llvm/tools/clang/tools
svn co -q ${LLVM_BASE}/clang-tools-extra/${TAG} extra
popd
pushd llvm/projects
svn co -q ${LLVM_BASE}/libcxx/${TAG} libcxx
svn co -q ${LLVM_BASE}/libcxxabi/${TAG} libcxxabi
svn co -q ${LLVM_BASE}/compiler-rt/${TAG} compiler-rt
popd

mkdir build
cd build
cmake -G "Unix Makefiles" ../llvm \
    -DCMAKE_BUILD_TYPE:STRING=Release \
    -DCMAKE_INSTALL_PREFIX:PATH=/root/staging \
    -DLLVM_BINUTILS_INCDIR:PATH=/opt/compiler-explorer/gcc-7.2.0/lib/gcc/x86_64-linux-gnu/7.2.0/plugin/include/ \
    -DLLVM_EXPERIMENTAL_TARGETS_TO_BUILD="RISCV;WebAssembly"

make -j$(nproc) install

# Don't try to compress the binaries as they don't like it

export XZ_DEFAULTS="-T 0"
tar Jcf ${OUTPUT} --transform "s,^./,./clang-${VERSION}/," -C ${STAGING_DIR} .

if [[ ! -z "${S3OUTPUT}" ]]; then
    s3cmd put --rr ${OUTPUT} ${S3OUTPUT}
fi
