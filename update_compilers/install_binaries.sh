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
# cmake

if [[ ! -x ${OPT}/cmake/bin/cmake ]]; then
    mkdir cmake
    fetch https://github.com/Kitware/CMake/releases/download/v3.18.2/cmake-3.18.2-Linux-x86_64.tar.gz | tar zxf - --strip-components 1 -C cmake
fi


#########################
# pahole

TARGET_PAHOLE_VERSION=v1.19
CURRENT_PAHOLE_VERSION=""
if [[ -f ${OPT}/pahole/bin/pahole ]]; then
    CURRENT_PAHOLE_VERSION=$(${OPT}/pahole/bin/pahole --version)
fi

if [[ "$TARGET_PAHOLE_VERSION" != "$CURRENT_PAHOLE_VERSION" ]]; then
    rm -Rf ${OPT}/pahole
    mkdir -p ${OPT}/pahole

    mkdir -p /tmp/build
    pushd /tmp/build

    # Install elfutils for libelf and libdwarf
    fetch https://sourceware.org/elfutils/ftp/0.182/elfutils-0.182.tar.bz2 | tar jxf -
    pushd elfutils-0.182
    ./configure --prefix=/opt/compiler-explorer/pahole --program-prefix="eu-" --enable-deterministic-archives --disable-debuginfod --disable-libdebuginfod
    make -j$(nproc)
    make install
    popd

    rm -Rf /tmp/build/pahole

    git clone -q https://git.kernel.org/pub/scm/devel/pahole/pahole.git pahole
    git -C pahole checkout v1.19
    git -C pahole submodule sync
    git -C pahole submodule update --init
    pushd pahole
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
# x86-to-6502 old version

if [[ ! -f ${OPT}/x86-to-6502/lefticus/x86-to-6502 ]]; then
    mkdir -p ${OPT}/x86-to-6502/lefticus

    mkdir -p /tmp/build
    pushd /tmp/build

    git clone https://github.com/lefticus/x86-to-6502.git lefticus
    pushd lefticus
    git checkout 2a2ce54d32097558b81d014039309b68bce7aed8
    ${OPT}/cmake/bin/cmake .
    make
    mv x86-to-6502 ${OPT}/x86-to-6502/lefticus
    popd

    popd
    rm -rf /tmp/build
fi

#########################
# x86-to-6502 new version

if [[ ! -f ${OPT}/x86-to-6502/lefticus/6502-c++ ]]; then
    mkdir -p ${OPT}/x86-to-6502/lefticus

    mkdir -p /tmp/build
    pushd /tmp/build

    git clone https://github.com/lefticus/6502-cpp.git lefticus
    pushd lefticus
    mkdir -p build
    cd build
    CXX=/opt/compiler-explorer/gcc-10.2.0/bin/g++ ${OPT}/cmake/bin/cmake ..
    make 6502-c++
    mv bin/6502-c++ ${OPT}/x86-to-6502/lefticus
    popd

    popd
    rm -rf /tmp/build
fi

#########################
# xa 6502 cross compiler

if [[ ! -f ${OPT}/x86-to-6502/xa/bin/xa ]]; then
    mkdir -p ${OPT}/x86-to-6502/xa/bin

    mkdir -p /tmp/build
    pushd /tmp/build

    curl https://www.floodgap.com/retrotech/xa/dists/xa-2.3.13.tar.gz | tar xzf -
    cd xa-2.3.13

    make xa uncpk
    mv xa ${OPT}/x86-to-6502/xa/bin/xa
    mv reloc65 ${OPT}/x86-to-6502/xa/bin/reloc65
    mv ldo65 ${OPT}/x86-to-6502/xa/bin/ldo65
    mv file65 ${OPT}/x86-to-6502/xa/bin/file65
    mv printcbm ${OPT}/x86-to-6502/xa/bin/printcbm
    mv uncpk ${OPT}/x86-to-6502/xa/bin/uncpk

    cd ..

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
