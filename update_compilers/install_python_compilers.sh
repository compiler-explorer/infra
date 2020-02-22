#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. ${SCRIPT_DIR}/common.inc

get_python() {
    local VER=$1
    local DIR=Python-$VER

    if [[ ! -d ${DIR} ]]; then
        mkdir $DIR
        pushd $DIR

        fetch "https://www.python.org/ftp/python/${VER}/Python-${VER}.tgz" | tar xfz -
        cd $DIR

        ./configure --prefix=${OPT}/python --exec-prefix=${OPT}/python --without-ensurepip
        make
        make altinstall

        popd
    fi
}

for version in \
    3.5.9 \
    3.6.9 \
    3.7.6 \
    3.8.1; do
    get_python $version
done
