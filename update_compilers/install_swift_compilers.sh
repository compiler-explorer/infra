#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. ${SCRIPT_DIR}/common.inc

install_nightly() {
    if [[ "$ARG1" == "nightly" ]]; then
        return 0
    else
        return 1
    fi
}

get_swift() {
    local VER=$1
    local DIR=swift-${VER}

    local BUILD=swift-${VER}-release
    local TOOLCHAIN=swift-${VER}-RELEASE

    if [[ "$VER" == "nightly" ]]; then
        TOOLCHAIN=$(fetch https://swift.org/builds/development/ubuntu1604/latest-build.yml |
            grep '^download:' |
            awk '{print $2}' |
            sed 's/-ubuntu16\.04\.tar\.gz//g')
        BUILD=development
    fi

    if [[ ! -d ${DIR} ]]; then
        mkdir ${DIR}
        pushd ${DIR}
        fetch https://swift.org/builds/${BUILD}/ubuntu1604/${TOOLCHAIN}/${TOOLCHAIN}-ubuntu16.04.tar.gz | tar zxf - --strip-components 1
        # work around insane installation issue
        chmod og+r ./usr/lib/swift/CoreFoundation/*
        popd
    fi
}

get_swift 3.1.1
get_swift 4.0.2
get_swift 4.0.3
get_swift 4.1
get_swift 4.1.1
get_swift 4.1.2
get_swift 4.2
get_swift 5.0
get_swift 5.1

if install_nightly; then
    get_swift nightly
fi
