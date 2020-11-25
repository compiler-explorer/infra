#!/bin/bash

# This script installs all the libraries to be used by Compiler Explorer

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.inc
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

TARGET_NODE_VERSION=v12.18.4
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
# cmake

if [[ ! -x ${OPT}/cmake/bin/cmake ]]; then
    mkdir cmake
    fetch https://github.com/Kitware/CMake/releases/download/v3.18.2/cmake-3.18.2-Linux-x86_64.tar.gz | tar zxf - --strip-components 1 -C cmake
fi


#########################
# pahole

if [[ ! -d ${OPT}/pahole ]]; then
    mkdir ${OPT}/pahole

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
    ${OPT}/cmake/bin/cmake \
        -D CMAKE_INSTALL_PREFIX:PATH=${OPT}/pahole \
        -D__LIB=lib \
        -DCMAKE_INSTALL_RPATH_USE_LINK_PATH=TRUE \
        .
    make -j$(nproc)
    make install
    popd

    popd
    rm -rf /tmp/build
fi

#########################
# x86-to-6502

if [[ ! -d ${OPT}/x86-to-6502/lefticus ]]; then
    mkdir -p ${OPT}/x86-to-6502/lefticus

    mkdir -p /tmp/build
    pushd /tmp/build

    git clone https://github.com/lefticus/x86-to-6502.git lefticus
    pushd lefticus
    ${OPT}/cmake/bin/cmake .
    make
    mv x86-to-6502 ${OPT}/x86-to-6502/lefticus
    popd

    popd
    rm -rf /tmp/build
fi

#########################
# iwyu - include-what-you-use

if [[ ! -d ${OPT}/iwyu/0.12 ]]; then
    mkdir -p /tmp/build
    pushd /tmp/build

    curl https://include-what-you-use.org/downloads/include-what-you-use-0.12.src.tar.gz | tar xzf -
    cd include-what-you-use/
    mkdir build
    cd build
    ${OPT}/cmake/bin/cmake .. -DCMAKE_PREFIX_PATH=${OPT}/clang-8.0.0/ -DCMAKE_INSTALL_PREFIX=${OPT}/iwyu/0.12
    ${OPT}/cmake/bin/cmake --build . --target install
    ln -s ${OPT}/clang-8.0.0/lib ${OPT}/iwyu/0.12/lib

    popd
    rm -rf /tmp/build
fi


#########################
# plog-converter
if [[ ! -x ${OPT}/plog-converter ]]; then
    mkdir -p /tmp/build
    pushd /tmp/build

    git clone https://github.com/viva64/plog-converter.git
    cd plog-converter
    mkdir build
    cd build
    ${OPT}/cmake/bin/cmake ..
    ${OPT}/cmake/bin/cmake --build .
    cp plog-converter ${OPT}/plog-converter

    popd
    rm -rf /tmp/build
fi
