#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. ${SCRIPT_DIR}/common.inc

getnim() {
    vers=$1
    if [[ -d nim-${vers} ]]; then
        echo Nim ${vers} already installed, skipping
        return
    fi
    mkdir nim-${vers}
    pushd nim-${vers}

    fetch https://nim-lang.org/download/nim-${vers}-linux_x64.tar.xz | tar Jxf - --transform="s/nim-${vers}/./"
    do_strip bin
    popd
}

getnim 1.0.4
