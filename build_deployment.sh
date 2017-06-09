#!/usr/bin/env bash

set -ex
DIR=$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )

SHA=${1}
OUTPUT=$(realpath ${2})
DEPLOY_DIR=$(mktemp -d /tmp/ce-build-XXXXXXXX)

rm -rf ${DEPLOY_DIR}
mkdir -p ${DEPLOY_DIR}
cd ${DEPLOY_DIR}
git clone https://github.com/mattgodbolt/compiler-explorer.git
cd compiler-explorer
git reset --hard ${SHA}

add_path() {
    local new_path=$1
    if [[ ! -d "${new_path}" ]]; then
        echo "Unable to find path at ${new_path}"
        exit 1
    fi
    PATH=${new_path}:$PATH
}

add_path /opt/compiler-explorer/gdc5.2.0/x86_64-pc-linux-gnu/bin
add_path /opt/compiler-explorer/rust-1.14.0/bin
add_path /opt/compiler-explorer/node/bin
add_path /opt/compiler-explorer/ghc-8.0.2/bin
make -j$(nproc) dist

tar Jcvf ${OUTPUT} .

rm -rf ${DEPLOY_DIR}
