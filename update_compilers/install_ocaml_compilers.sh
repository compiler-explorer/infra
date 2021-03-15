#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.inc
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
get_ocaml 4.08.1
get_ocaml 4.09.0
get_ocaml 4.09.1
get_ocaml 4.10.0
get_ocaml 4.10.1
get_ocaml 4.10.2
get_ocaml 4.11.1
get_ocaml 4.11.2
get_ocaml 4.12.0

get_ocaml 4.07.1-flambda
get_ocaml 4.08.1-flambda
get_ocaml 4.09.0-flambda
get_ocaml 4.09.1-flambda
get_ocaml 4.10.0-flambda
get_ocaml 4.10.1-flambda
get_ocaml 4.10.2-flambda
get_ocaml 4.11.1-flambda
get_ocaml 4.11.2-flambda
get_ocaml 4.12.0-flambda
