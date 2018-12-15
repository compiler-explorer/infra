#!/bin/bash

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
. ${SCRIPT_DIR}/common.inc

get_ocaml() {
    local VER=$1
    local DIR=ocaml-$VER

    if [[ ! -d ${DIR} ]]; then
        pushd /tmp
        fetch https://github.com/ocaml/ocaml/archive/${VER}.tar.gz | tar zxf -
        cd /tmp/ocaml-${VER}
        ./configure -prefix ${OPT}/${DIR}
        make world.opt
        make install
        popd
    fi
}

get_ocaml_flambda() {
    local VER=$1
    local DIR=ocaml-$VER+flambda

    if [[ ! -d ${DIR} ]]; then
        pushd /tmp
        fetch https://github.com/ocaml/ocaml/archive/${VER}.tar.gz | tar zxf -
        cd /tmp/ocaml-${VER}
        ./configure -flambda -prefix ${OPT}/${DIR}
        make world.opt
        make install
        popd
    fi
}

get_ocaml 4.04.2
get_ocaml 4.06.1
get_ocaml 4.07.1

get_ocaml_flambda 4.07.1
