#!/bin/bash

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
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
        echo Golang ${VERSION} already intalled, skipping
        return
    fi
    mkdir ${DIR}
    pushd ${DIR}
    fetch https://storage.googleapis.com/golang/go${VERSION}.linux-amd64.tar.gz | tar zxf -
    popd
    do_strip ${DIR}
}

install_golang 1.7.2
install_golang 1.8.5
install_golang 1.8.7
install_golang 1.9.2
install_golang 1.9.4
install_golang 1.10
install_golang 1.10.1
install_golang 1.11
