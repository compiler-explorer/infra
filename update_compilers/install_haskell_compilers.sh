#!/bin/bash

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
. ${SCRIPT_DIR}/common.inc


get_ghc() {
    local VER=$1
    local DIR=ghc-$VER

    if [[ ! -d ${DIR} ]]; then
        pushd /tmp
        fetch https://downloads.haskell.org/~ghc/${VER}/ghc-${VER}-x86_64-deb8-linux.tar.xz | tar Jxf -
        cd /tmp/ghc-${VER}
        ./configure --prefix=${OPT}/${DIR}
        make install
        popd
    fi
}

get_ghc 8.0.2
# Can't install ghc 8.2.1: https://ghc.haskell.org/trac/ghc/ticket/13945
# get_ghc 8.2.1
get_ghc 8.2.2
get_ghc 8.4.1
get_ghc 8.4.2
get_ghc 8.4.3
get_ghc 8.4.4
get_ghc 8.6.1
get_ghc 8.6.2
