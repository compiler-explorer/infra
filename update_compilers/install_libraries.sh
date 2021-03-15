#!/bin/bash

# This script installs all the libraries to be used by Compiler Explorer

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.inc
. ${SCRIPT_DIR}/common.inc

export PATH=$PATH:/opt/compiler-explorer/cmake/bin

if install_nightly; then
    echo "Installing trunk versions"
else
    echo "Skipping install of trunk versions"
fi

#########################
# C++

ce_install 'libraries'
ce_squash 'libraries'

#########################
# OpenSSL

install_openssl() {
    for VERSION in "$@"; do
        local DEST=${OPT}/libs/openssl/openssl_${VERSION}/x86_64/opt
        if [[ ! -d ${DEST} ]]; then
            rm -rf /tmp/openssl
            mkdir -p /tmp/openssl
            pushd /tmp/openssl
            fetch https://github.com/openssl/openssl/archive/OpenSSL_${VERSION}.tar.gz | tar zxf - --strip-components 1

            setarch i386 ./config -m32 --prefix=${OPT}/libs/openssl/openssl_${VERSION}/x86/opt --openssldir=${OPT}/libs/openssl/openssl_${VERSION}/x86/ssl
            make
            make install
            rm ${OPT}/libs/openssl/openssl_${VERSION}/x86/opt/lib/*.a

            make clean
            ./config --prefix=${OPT}/libs/openssl/openssl_${VERSION}/x86_64/opt --openssldir=${OPT}/libs/openssl/openssl_${VERSION}/x86_64/ssl
            make
            make install
            rm ${OPT}/libs/openssl/openssl_${VERSION}/x86_64/opt/lib/*.a
            popd

            rm -rf /tmp/openssl
        fi
    done
}

install_openssl 1_1_1c 1_1_1g

#########################
# cs50

install_cs50_v9() {
    for VERSION in "$@"; do
        local DEST1=${OPT}/libs/cs50/${VERSION}/x86_64/lib
        local DEST2=${OPT}/libs/cs50/${VERSION}/x86/lib
        local INC=${OPT}/libs/cs50/${VERSION}/include
        if [[ ! -d ${DEST1} ]]; then
            rm -rf /tmp/cs50
            mkdir -p /tmp/cs50
            pushd /tmp/cs50
            fetch https://github.com/cs50/libcs50/archive/v${VERSION}.tar.gz | tar zxf - --strip-components 1

            env CFLAGS="-Wall -Wextra -Werror -pedantic -std=c99 -march=native" make -e
            mkdir -p ${DEST1}
            mv build/lib/* ${DEST1}

            mkdir -p ${INC}
            cp -Rf build/include/* ${INC}

            env CFLAGS="-Wall -Wextra -Werror -pedantic -std=c99 -m32" make -e
            mkdir -p ${DEST2}
            mv build/lib/* ${DEST2}

            cd ${DEST1}
            ln -s libcs50.so.${VERSION} libcs50.so.9
            cd ${DEST2}
            ln -s libcs50.so.${VERSION} libcs50.so.9

            popd

            rm -rf /tmp/cs50
        fi
    done
}

install_cs50_v9 9.1.0

#########################
# libuv

install_libuv() {
    for VERSION in "$@"; do
        local DEST1=${OPT}/libs/libuv/v${VERSION}/x86_64/lib
        local DEST2=${OPT}/libs/libuv/v${VERSION}/x86/lib
        if [[ ! -d ${DEST1} ]]; then
            rm -rf /tmp/libuv
            mkdir -p /tmp/libuv
            pushd /tmp/libuv

            fetch https://github.com/libuv/libuv/archive/v${VERSION}.tar.gz | tar zxf - --strip-components 1

            mkdir -p build
            cd build
            cmake -DCMAKE_BUILD_TYPE=Release ..
            cd ..
            cmake --build build --target uv

            mkdir -p ${DEST1}
            mv build/libuv.so* ${DEST1}

            rm -Rf build

            mkdir -p build
            cd build
            cmake -DCMAKE_BUILD_TYPE=Release -DCMAKE_C_FLAGS=-m32 ..
            cd ..
            cmake --build build --target uv

            mkdir -p ${DEST2}
            mv build/libuv.so* ${DEST2}

            popd

            rm -rf /tmp/libuv
        fi
    done
}

#########################
# lua

install_lua() {
    for VERSION in "$@"; do
        local DEST1=${OPT}/libs/lua/${VERSION}/lib/x86_64
        local DEST2=${OPT}/libs/lua/${VERSION}/lib/x86
        local DEST3=${OPT}/libs/lua/${VERSION}/include
        if [[ ! -d ${DEST1} ]]; then
            rm -rf /tmp/lua
            mkdir -p /tmp/lua
            pushd /tmp/lua

            git clone -b ${VERSION} https://github.com/lua/lua
            cd lua

            mkdir -p ${DEST3}

            cp *.h ${DEST3}

            rm -f onelua.c
            local cfiles=$(find . -maxdepth 1 -iname '*.c' -o -iname '*.h')
            echo -e "cmake_minimum_required(VERSION 3.10)\n" >CMakeLists.txt
            echo -e "project(lua LANGUAGES C)\n" >>CMakeLists.txt
            echo -e "add_library(lua SHARED\n" >>CMakeLists.txt
            echo -e ${cfiles} >>CMakeLists.txt
            echo -e ")\n" >>CMakeLists.txt

            mkdir -p build
            cd build
            cmake "-DCMAKE_BUILD_TYPE=Debug" "-DCMAKE_C_FLAGS_DEBUG=-std=gnu99 -O2 -Wall -Wl,-E -ldl -DLUA_USE_POSIX -DLUA_USE_DLOPEN" ..
            make

            mkdir -p ${DEST1}
            cp liblua.so ${DEST1}

            cd ..
            rm -Rf build

            mkdir -p build
            cd build
            cmake "-DCMAKE_BUILD_TYPE=Debug" "-DCMAKE_C_FLAGS_DEBUG=-std=gnu99 -O2 -Wall -Wl,-E -ldl -m32 -DLUA_USE_POSIX -DLUA_USE_DLOPEN" ..
            make

            mkdir -p ${DEST2}
            cp liblua.so ${DEST2}

            popd
            rm -rf /tmp/lua
        fi
    done
}

install_lua v5.3.5 v5.4.0
