#!/bin/bash

# This script installs all the libraries to be used by Compiler Explorer

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.inc
. "${DIR}/common.inc"

#########################
# cmake

if [[ ! -x ${OPT}/cmake-v3.18.2/bin/cmake ]]; then
    cd "${OPT}"
    mkdir cmake-v3.18.2
    fetch https://github.com/Kitware/CMake/releases/download/v3.18.2/cmake-3.18.2-Linux-x86_64.tar.gz | tar zxf - --strip-components 1 -C cmake-v3.18.2
fi

if [[ ! -x ${OPT}/cmake-v3.23.1/bin/cmake ]]; then
    cd "${OPT}"
    mkdir cmake-v3.23.1
    fetch https://github.com/Kitware/CMake/releases/download/v3.23.1/cmake-3.23.1-Linux-x86_64.tar.gz | tar zxf - --strip-components 1 -C cmake-v3.23.1
fi

if [[ ! -x ${OPT}/cmake-v3.25.0-rc2/bin/cmake ]]; then
    cd "${OPT}"
    mkdir cmake-v3.25.0-rc2
    fetch https://github.com/Kitware/CMake/releases/download/v3.25.0-rc2/cmake-3.25.0-rc2-Linux-x86_64.tar.gz | tar zxf - --strip-components 1 -C cmake-v3.25.0-rc2
fi

rm -Rf "${OPT}/cmake"
ln -s "${OPT}/cmake-v3.25.0-rc2" "${OPT}/cmake"

#########################
# pahole

TARGET_PAHOLE_VERSION=v1.19
CURRENT_PAHOLE_VERSION=""
if [[ -f "${OPT}/pahole/bin/pahole" ]]; then
    CURRENT_PAHOLE_VERSION=$("${OPT}/pahole/bin/pahole" --version)
fi

if [[ "$TARGET_PAHOLE_VERSION" != "$CURRENT_PAHOLE_VERSION" ]]; then
    rm -Rf "${OPT}/pahole"
    mkdir -p "${OPT}/pahole"

    mkdir -p /tmp/build
    pushd /tmp/build

    # Install elfutils for libelf and libdwarf
    fetch https://sourceware.org/elfutils/ftp/0.182/elfutils-0.182.tar.bz2 | tar jxf -
    pushd elfutils-0.182
    ./configure --prefix=/opt/compiler-explorer/pahole --program-prefix="eu-" --enable-deterministic-archives --disable-debuginfod --disable-libdebuginfod
    make "-j$(nproc)"
    make install
    popd

    rm -Rf /tmp/build/pahole

    git clone -q https://git.kernel.org/pub/scm/devel/pahole/pahole.git pahole
    git -C pahole checkout v1.19
    git -C pahole submodule sync
    git -C pahole submodule update --init
    pushd pahole
    "${OPT}/cmake/bin/cmake" \
        -D CMAKE_INSTALL_PREFIX:PATH="${OPT}/pahole" \
        -D__LIB=lib \
        -DCMAKE_INSTALL_RPATH_USE_LINK_PATH=TRUE \
        .
    make "-j$(nproc)"
    make install
    popd

    popd
    rm -rf /tmp/build
fi

#########################
# x86-to-6502 old version

if [[ ! -f ${OPT}/x86-to-6502/lefticus/x86-to-6502 ]]; then
    mkdir -p "${OPT}/x86-to-6502/lefticus"

    mkdir -p /tmp/build
    pushd /tmp/build

    git clone https://github.com/lefticus/x86-to-6502.git lefticus
    pushd lefticus
    git checkout 2a2ce54d32097558b81d014039309b68bce7aed8
    "${OPT}/cmake/bin/cmake" .
    make
    mv x86-to-6502 "${OPT}/x86-to-6502/lefticus"
    popd

    popd
    rm -rf /tmp/build
fi

# x86-to-6502 new version (6502-c++) is built by misc-builder

#########################
# iwyu - include-what-you-use

if [[ ! -d ${OPT}/iwyu/0.12 ]]; then
    mkdir -p /tmp/build
    pushd /tmp/build

    curl https://include-what-you-use.org/downloads/include-what-you-use-0.12.src.tar.gz | tar xzf -
    cd include-what-you-use/
    mkdir build
    cd build
    "${OPT}/cmake/bin/cmake" .. -DCMAKE_PREFIX_PATH="${OPT}/clang-8.0.0/" -DCMAKE_INSTALL_PREFIX="${OPT}/iwyu/0.12"
    "${OPT}/cmake/bin/cmake" --build . --target install
    ln -s "${OPT}/clang-8.0.0/lib" "${OPT}/iwyu/0.12/lib"

    popd
    rm -rf /tmp/build
fi
