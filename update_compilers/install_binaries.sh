#!/bin/bash

# This script installs all the libraries to be used by Compiler Explorer

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
. ${DIR}/common.inc


#########################
# patchelf
if [[ ! -f ${PATCHELF} ]]; then
    fetch http://nixos.org/releases/patchelf/patchelf-0.8/patchelf-0.8.tar.gz | tar zxf -
    pushd patchelf-0.8
    CFLAGS=-static LDFLAGS=-static CXXFLAGS=-static ./configure
    make -j$(nproc)
    popd
fi


#########################
# node.js

TARGET_NODE_VERSION=v10.15.3
CURRENT_NODE_VERSION=""
if [[ -d node ]]; then
    CURRENT_NODE_VERSION=$(node/bin/node --version)
fi

if [[ "$TARGET_NODE_VERSION" != "$CURRENT_NODE_VERSION" ]]; then
    echo "Installing node TARGET_NODE_VERSION"
    rm -rf node
    fetch "https://nodejs.org/dist/${TARGET_NODE_VERSION}/node-${TARGET_NODE_VERSION}-linux-x64.tar.gz" | tar zxf - && mv node-${TARGET_NODE_VERSION}-linux-x64 node
fi

#########################
# yarn

TARGET_YARN_VERSION=v1.13.0
CURRENT_YARN_VERSION=""
if [[ -f yarn/bin/yarn.js ]]; then
    CURRENT_YARN_VERSION="v$(node/bin/node yarn/bin/yarn.js --version)"
fi

if [[ "$TARGET_YARN_VERSION" != "$CURRENT_YARN_VERSION" ]]; then
    echo "Installing yarn TARGET_YARN_VERSION"
    rm -rf yarn
    mkdir yarn
    fetch "https://github.com/yarnpkg/yarn/releases/download/${TARGET_YARN_VERSION}/yarn-${TARGET_YARN_VERSION}.tar.gz" | tar zxf - -C yarn --strip-components=1
fi

#########################
# pahole

if [[ ! -d /opt/compiler-explorer/pahole ]]; then
    mkdir /opt/compiler-explorer/pahole

    mkdir -p /tmp/build
    pushd /tmp/build

    # Install elfutils for libelf and libdwarf
    fetch https://sourceware.org/elfutils/ftp/0.175/elfutils-0.175.tar.bz2 | tar jxf -
    pushd elfutils-0.175
    ./configure --prefix=/opt/compiler-explorer/pahole --program-prefix="eu-" --enable-deterministic-archives
    make -j$(nproc)
    make install
    popd

    fetch https://git.kernel.org/pub/scm/devel/pahole/pahole.git/snapshot/pahole-1.12.tar.gz | tar zxf -
    pushd pahole-1.12
    /opt/compiler-explorer/cmake/bin/cmake \
        -D CMAKE_INSTALL_PREFIX:PATH=/opt/compiler-explorer/pahole \
        -D__LIB=lib \
        -DCMAKE_INSTALL_RPATH_USE_LINK_PATH=TRUE \
        .
    make -j$(nproc)
    make install
    popd

    popd
    rm -rf /tmp/build
fi
