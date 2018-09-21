#!/bin/bash

ARG1="$1"

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
. ${SCRIPT_DIR}/common.inc ${ARG1}

install_zig() {
    local VERSION=$1
    local AUTOMATED_BUILD=$2
    local DIR=zig-${VERSION}
    if [[ -d ${DIR} ]]; then
        echo Zig $VERSION already installed, skipping
        return
    fi
    mkdir ${DIR}
    pushd ${DIR}

    if [ -z "$AUTOMATED_BUILD" ]; then
        fetch https://ziglang.org/download/${VERSION}/zig-linux-x86_64-${VERSION}.tar.xz | tar Jxf - --strip-components 1
    else
        fetch https://ziglang.org/builds/zig-linux-x86_64-${VERSION}.tar.xz | tar Jxf - --strip-components 1
    fi

    rm -f langref.html

    popd
    do_strip ${DIR}
}

if install_nightly; then
    install_zig master 1
fi
