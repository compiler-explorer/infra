#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. ${SCRIPT_DIR}/common.inc

# This naming scheme is getting ridiculous
get_ispc_new() {
    local VER=$1
    local DIR=ispc-$VER

    if [[ ! -d ${DIR} ]]; then
        mkdir $DIR
        pushd $DIR
        fetch https://sourceforge.net/projects/ispcmirror/files/v$VER/ispc-v$VER-linux.tar.gz/download |
            tar zxf - ispc-v$VER-linux --strip-components 1
        popd
        do_strip $DIR
    fi
}
get_ispc() {
    local VER=$1
    local DIR=ispc-$VER

    if [[ ! -d ${DIR} ]]; then
        mkdir $DIR
        pushd $DIR
        fetch https://sourceforge.net/projects/ispcmirror/files/v$VER/ispc-v$VER-linux.tar.gz/download |
            tar zxf - ispc-$VER-Linux --strip-components 1
        popd
        do_strip $DIR
    fi
}
get_ispc_old() {
    local VER=$1
    local DIR=ispc-$VER

    if [[ ! -d ${DIR} ]]; then
        mkdir $DIR
        pushd $DIR
        fetch https://sourceforge.net/projects/ispcmirror/files/v$VER/ispc-v$VER-linux.tar.gz/download |
            tar zxf - ispc-v$VER-linux-ispc --strip-components 1
        popd
        do_strip $DIR
    fi
}

do_ispc_nightly_install() {
    local COMPILER_PATTERN="$1"
    local DESTINATION="$2"

    # just shell out to the new install system
    ce_install "compilers/ispc/nightly ${COMPILER_PATTERN}"

    # new systtem doesn't yet clean up old nightly installs, so we have to do it here still

    # work around a cronic issue where the execution output is interpreted as error
    # if it spans multiple lines: assigning output with multiple lines to a variable
    # fools it.
    set +x
    compilers=$(ls "${OPT}" | grep -oE "${DESTINATION}-[0-9]+" | sort)
    set -x
    compiler_array=(${compilers})
    latest=${compiler_array[-1]}

    # Clean up any old snapshots
    for compiler in ${DESTINATION}-[0-9]*; do
        if [[ -d ${compiler} ]]; then
            if [[ "${compiler}" != "${latest}" ]]; then
                rm -rf ${compiler}
            fi
        fi
    done
}
get_ispc_new 1.12.0
get_ispc 1.10.0
get_ispc_old 1.9.2
get_ispc_old 1.9.1

if install_nightly; then
    do_ispc_nightly_install trunk ispc-trunk
fi
