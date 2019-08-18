#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. ${SCRIPT_DIR}/common.inc

## Install 1.4.1 the old way...
if [[ ! -d ${OPT}/go ]]; then
    fetch https://storage.googleapis.com/golang/go1.4.1.linux-amd64.tar.gz | tar zxf -
    do_strip ${OPT}/go
fi

install_golang() {
    local VERSION=$1
    local DIR=golang-${VERSION}
    if [[ -d ${DIR} ]]; then
        echo Golang ${VERSION} already installed, skipping
        return
    fi
    mkdir ${DIR}
    pushd ${DIR}
    fetch https://storage.googleapis.com/golang/go${VERSION}.linux-amd64.tar.gz | tar zxf -
    popd
    do_strip ${DIR}
}

do_nightly_install() {
    local COMPILER_PATTERN="$1"
    local DESTINATION="$2"
    # work around a cronic issue where the execution output is interpreted as error
    # if it spans multiple lines: assigning output with multiple lines to a variable
    # fools it.
    set +x
    compilers=$(echo $ALL_COMPILERS | grep -oE "${COMPILER_PATTERN}-[0-9]+" | sort)
    set -x
    compiler_array=(${compilers})
    latest=${compiler_array[-1]}
    # Extract the latest...
    if [[ ! -d ${latest} ]]; then
        fetch ${S3URL}/${latest}.tar.xz | tar Jxf -
    fi
    # Ensure the symlink points at the latest
    rm -f ${OPT}/${DESTINATION}
    ln -s ${latest} ${OPT}/${DESTINATION}
    # Clean up any old snapshots
    for compiler in ${COMPILER_PATTERN}-[0-9]*; do
        if [[ -d ${compiler} ]]; then
            if [[ "${compiler}" != "${latest}" ]]; then
                rm -rf ${compiler}
            fi
        fi
    done
}

install_golang 1.7.2
install_golang 1.8.5
install_golang 1.8.7
install_golang 1.9.2
install_golang 1.9.4
install_golang 1.10
install_golang 1.10.1
install_golang 1.11
install_golang 1.12

if install_nightly; then
    do_nightly_install go-trunk go-tip
fi
