#!/bin/bash

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
. ${SCRIPT_DIR}/common.inc


install_nightly() {
    if [[ "$ARG1" = "nightly" ]]; then
        return 0
    else
        return 1
    fi
}

get_swift() {
    local VER=$1
    local DIR=swift-${VER}

    if [[ ! -d ${DIR} ]]; then
        mkdir ${DIR}
        pushd ${DIR}
        fetch https://swift.org/builds/swift-${VER}-release/ubuntu1604/swift-${VER}-RELEASE/swift-${VER}-RELEASE-ubuntu16.04.tar.gz | tar zxf - --strip-components 1
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
