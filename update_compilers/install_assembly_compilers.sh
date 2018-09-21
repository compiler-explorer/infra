#!/bin/bash

ARG1="$1"

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
. ${SCRIPT_DIR}/common.inc ${ARG1}


get_nasm() {
    local VER=$1
    local DIR=nasm-$VER

    if [[ ! -d ${OPT}/${DIR} ]]; then
        pushd /tmp
        fetch https://www.nasm.us/pub/nasm/releasebuilds/${VER}/nasm-${VER}.tar.xz | tar Jxf -
        cd ${DIR}
        sh configure
        make
        mkdir ${OPT}/${DIR}
        cp nasm ${OPT}/${DIR}
        popd
    fi
}

for version in \
    2.12.02 \
    2.13.02 \
    2.13.03 \
; do
    get_nasm $version
done
