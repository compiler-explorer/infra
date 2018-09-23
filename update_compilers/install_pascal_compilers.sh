#!/bin/bash

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
. ${SCRIPT_DIR}/common.inc


get_fpc() {
    local VER=$1
    local DIR=fpc-$VER.x86_64-linux

    if [[ ! -d ${OPT}/${DIR} ]]; then
        pushd /tmp
        fetch https://downloads.sourceforge.net/project/freepascal/Linux/${VER}/fpc-${VER}.x86_64-linux.tar | tar xf -
        cd ${DIR}
        rm demo.tar.gz
        rm doc-pdf.tar.gz
        rm install.sh
        cp ${SCRIPT_DIR}/custom/install_fpc.sh .
        . install_fpc.sh $VER ${OPT}/${DIR}
        popd
    fi
}

for version in \
    2.6.0 \
    2.6.2 \
    2.6.4 \
    3.0.2 \
    3.0.4 \
; do
    get_fpc $version
done

if [[ ! -d ${OPT}/fpc ]]; then
    mkdir ${OPT}/fpc
fi
cp ${SCRIPT_DIR}/custom/fpc.cfg ${OPT}/fpc/fpc.cfg
