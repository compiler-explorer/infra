#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. ${SCRIPT_DIR}/common.inc

getnim() {
    vers=$1
    if [[ -d nim-${vers} ]]; then
        echo Nim ${vers} already installed, skipping
        return
    fi
    mkdir nim-${vers}
    pushd nim-${vers}

    fetch https://nim-lang.org/download/nim-${vers}-linux_x64.tar.xz | tar Jxf - --transform="s/nim-${vers}/./"
    do_strip bin
    popd
}

getnimnighly() {
    set -x
    set -o errexit
    local target=$1
    local directory="nim-${target}-nightlies"

    local latest_release="https://api.github.com/repos/nim-lang/nightlies/releases/latest"
    local release_json=$(curl ${latest_release})
    local tag_name=$(echo ${release_json} | jq '.tag_name')

    if [[ -f ${directory}/VERSION ]] && [[ $(< ${directory}/VERSION) = ${tag_name} ]]; then
        echo "latest nightly Nim for ${target} already installed, skipping"
        return;
    fi;

    rm -fr ${directory};
    mkdir ${directory};
    pushd ${directory}
    # select the array of assets whose name contains the desired target
    # build an array in case there are multiple results and get the first element
    local get_archive_url="[.assets[] | select(.name | contains(\"${target}\"))][0].browser_download_url"
    local archive_url=$(echo ${release_json} | jq -j "${get_archive_url}")
    # --transform moves everything inside the root directory nim-.../ into the current directory
    fetch ${archive_url} | tar Jxf - --transform="s,nim-[^/]*,.,"
    do_strip bin
    echo ${tag_name} >> VERSION
    popd
}

getnim 1.0.4

if install_nightly; then
    getnimnighly "linux_x64"
fi;
