#!/bin/bash

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
. ${SCRIPT_DIR}/common.inc

get_ppci() {
  local VER=$1
  local DIR=ppci-${VER}

  if [[ ! -d ${DIR} ]]; then
    fetch https://pypi.io/packages/source/p/ppci/ppci-$VER.tar.gz | tar xfz -
  fi
}

get_ppci 0.5.5

for version in \
    1.27 \
; do
    if [[ ! -d gcc-${version} ]]; then
        compiler=gcc-${version}.tar.xz
        fetch ${S3URL}/${compiler} | tar Jxf -
    fi
done


do_nightly_install() {
    local COMPILER_PATTERN="$1"
    local DIR="$2"
    local DESTINATION="$3"
    # work around a cronic issue where the execution output is interpreted as error
    # if it spans multiple lines: assigning output with multiple lines to a variable
    # fools it.
    set +x
    compilers=$(echo ${ALL_COMPILERS} | grep -oE "${COMPILER_PATTERN}-[0-9]+" | sort)
    set -x
    compiler_array=(${compilers})
    latest=${compiler_array[-1]}
    pushd ${DIR}
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
    popd
}


for version in 2.17
do
    DIR=6502/cc65-${version}
    if [[ ! -d ${DIR} ]]; then
        mkdir -p 6502
        pushd 6502
        fetch ${S3URL}/cc65-${version}.tar.xz | tar Jxf -
        popd
    fi
done

if install_nightly; then
    do_nightly_install cc65-trunk 6502 cc65-trunk
fi