#!/bin/bash

# This script installs all the libraries to be used by Compiler Explorer

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. ${SCRIPT_DIR}/common.inc

ARG1="$1"
install_nightly() {
    if [[ "$ARG1" == "nightly" ]]; then
        return 0
    else
        return 1
    fi
}

if install_nightly; then
    echo "Installing trunk versions"
else
    echo "Skipping install of trunk versions"
fi

#########################
# C++

install_boost() {
    for VERSION in "$@"; do
        local VERSION_UNDERSCORE=$(echo ${VERSION} | tr . _)
        local DEST=${OPT}/libs/boost_${VERSION_UNDERSCORE}/boost/
        if [[ ! -d ${DEST} ]]; then
            mkdir -p /tmp/boost
            pushd /tmp/boost
            fetch https://dl.bintray.com/boostorg/release/${VERSION}/source/boost_${VERSION_UNDERSCORE}.tar.bz2 | tar jxf - boost_${VERSION_UNDERSCORE}/boost
            mkdir -p ${OPT}/libs/boost_${VERSION_UNDERSCORE}/boost
            rsync -a boost_${VERSION_UNDERSCORE}/boost/ ${DEST}
            popd
            rm -rf /tmp/boost
        fi
    done
}

update_boost_archive() {
    local NEWEST=$(find "${OPT}/libs" -maxdepth 1 -name 'boost*' -printf '%T@ %p\n' | sort -k1,1nr | head -n1 | cut -d ' ' -f 2)
    if [[ "${NEWEST}" != "${OPT}/libs/boost.tar.xz" ]]; then
        pushd ${OPT}/libs
        rm -rf /tmp/boost.tar.xz
        tar -cJf /tmp/boost.tar.xz boost_*
        mv /tmp/boost.tar.xz boost.tar.xz
        popd
    fi
}

###########################################
# !!!!!!!!!!!!!!! IMPORTANT !!!!!!!!!!!!!!!
###########################################
#
# When adding a new version of boost you must:
#  - run `sudo ~/infra/update_compilers/install_libraries.sh` on the admin node to generate an updated `${OPT}/libs/boost.tar.xz`
#  - run `make packer` from your own machine to build a new AMI with the new boost version baked in
#  - update the image_id values in `terraform/lc.tf` and commit/push
#  - run `terraform apply` from your own machine so the new images are used when launching new nodes
#  - run `ce --env=prod instances restart` so currently running nodes will rsync the new boost version
#
# This rather convoluted process is required because when new nodes start up they attempt to rsync missing boost versions to a local directory
# and this process can take quite a while, during which compilations using missing boost versions will error out.
# To mitigate this we bake any known boost versions into the AMIs using packer.
#
# See: https://github.com/mattgodbolt/compiler-explorer/issues/1771

install_boost 1.64.0 1.65.0 1.66.0 1.67.0 1.68.0 1.69.0 1.70.0 1.71.0 1.72.0 1.73.0
update_boost_archive

ce_install 'libraries'

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

install_openssl 1_1_1c

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
