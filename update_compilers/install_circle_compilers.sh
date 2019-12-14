#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. ${SCRIPT_DIR}/common.inc

get_circle_preview() {
    local VER=$1
    local DIR=circle-preview-${VER}

    if [[ ! -d ${DIR} ]]; then
        fetch http://circle-lang.org/debian/build_$VER.tgz | tar xfz -
    fi
}

get_circle_preview 81
