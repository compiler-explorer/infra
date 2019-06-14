#!/bin/bash

 SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
. ${SCRIPT_DIR}/common.inc

get_ocaml() {
    local VER=$1
    local DIR=ocaml-${VER}

    if [[ ! -d ${DIR} ]]; then
        fetch ${S3URL}/${DIR}.tar.xz | tar Jxf -
    fi
}
get_ocaml 4.04.2
get_ocaml 4.06.1
get_ocaml 4.07.1
get_ocaml 4.08.0

get_ocaml 4.07.1-flambda
get_ocaml 4.08.0-flambda
