#!/bin/bash

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
. ${SCRIPT_DIR}/common.inc

get_jdk() {
    local VERSION=$1
    local URL=$2
    local DIR=jdk-${VERSION}

    if [[ ! -d ${DIR} ]]; then
		mkdir ${DIR}
		pushd ${DIR}
        fetch ${URL} | tar zxf -
		popd
	fi
}

get_jdk1102() {
    get_jdk 11.0.2 https://download.java.net/java/GA/jdk11/9/GPL/openjdk-11.0.2_linux-x64_bin.tar.gz
}

get_jdk1201() {
    get_jdk 12.0.1 https://download.java.net/java/GA/jdk12.0.1/69cfe15208a647278a19ef0990eea691/12/GPL/openjdk-12.0.1_linux-x64_bin.tar.gz
}

get_jdk1102
get_jdk1201
