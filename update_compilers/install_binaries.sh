#!/bin/bash

# This script installs all the libraries to be used by Compiler Explorer

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.inc
. "${DIR}/common.inc"

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
