#!/bin/bash

set -exuo pipefail

finish() {
    ce builder stop
}
trap finish EXIT

ce builder status
ce builder start

BUILD_FAILED=0

init_logspout() {
    local LOG_DEST_HOST
    LOG_DEST_HOST=$(aws ssm get-parameter --name /compiler-explorer/logDestHost | jq -r .Parameter.Value)
    local LOG_DEST_PORT
    LOG_DEST_PORT=$(aws ssm get-parameter --name /compiler-explorer/logDestPort | jq -r .Parameter.Value)

    ce builder exec -- sudo docker pull gliderlabs/logspout:latest

    ce builder exec -- sudo docker stop logspout || true
    ce builder exec -- sudo docker rm logspout || true

    ce builder exec -- sudo docker run --name logspout \
        -d \
        -v=/var/run/docker.sock:/tmp/docker.sock \
        -e SYSLOG_HOSTNAME=librarybuilder \
        gliderlabs/logspout "syslog+tls://${LOG_DEST_HOST}:${LOG_DEST_PORT}"
}

build_cpp_libraries() {
    local BUILD_NAME=librarycpp
    local COMMAND=build.sh

    local CONAN_PASSWORD
    CONAN_PASSWORD=$(aws ssm get-parameter --name /compiler-explorer/conanpwd | jq -r .Parameter.Value)

    ce builder exec -- sudo docker run --rm --name "${BUILD_NAME}.build" \
        -v/home/ubuntu/.s3cfg:/root/.s3cfg:ro \
        -v/opt:/opt:ro \
        -e "CONAN_PASSWORD=${CONAN_PASSWORD}" \
        "compilerexplorer/library-builder" \
        bash "${COMMAND}" "c++" "all" "all" || true
}

build_rust_libraries() {
    local BUILD_NAME=libraryrust
    local COMMAND=build.sh

    local CONAN_PASSWORD
    CONAN_PASSWORD=$(aws ssm get-parameter --name /compiler-explorer/conanpwd | jq -r .Parameter.Value)

    ce builder exec -- sudo docker run --rm --name "${BUILD_NAME}.build" \
        -v/home/ubuntu/.s3cfg:/root/.s3cfg:ro \
        -v/opt:/opt:ro \
        -e "CONAN_PASSWORD=${CONAN_PASSWORD}" \
        "compilerexplorer/library-builder" \
        bash "${COMMAND}" "rust" "all" "all" || true
}

init_logspout
build_cpp_libraries
build_rust_libraries

exit ${BUILD_FAILED}
