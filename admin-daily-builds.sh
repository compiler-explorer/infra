#!/bin/bash

set -exuo pipefail

finish() {
    ce builder stop
}

ce builder status
ce builder start

BUILD_FAILED=0

build_cpp_libraries() {
    local BUILD_NAME=librarycpp
    local COMMAND=build.sh

    local CONAN_PASSWORD
    CONAN_PASSWORD=$(aws ssm get-parameter --name /compiler-explorer/conanpwd | jq -r .Parameter.Value)

    ce builder exec -- sudo docker run --rm --name "${BUILD_NAME}.build" \
        -v/home/ubuntu/.s3cfg:/root/.s3cfg:ro \
        -v/opt:/opt:ro \
        -e 'LOGSPOUT=ignore' \
        -e "CONAN_PASSWORD=${CONAN_PASSWORD}" \
        "compilerexplorer/library-builder" \
        bash "${COMMAND}" "c++" "all" "all"
}

build_rust_libraries() {
    local BUILD_NAME=libraryrust
    local COMMAND=build.sh

    local CONAN_PASSWORD
    CONAN_PASSWORD=$(aws ssm get-parameter --name /compiler-explorer/conanpwd | jq -r .Parameter.Value)

    ce builder exec -- sudo docker run --rm --name "${BUILD_NAME}.build" \
        -v/home/ubuntu/.s3cfg:/root/.s3cfg:ro \
        -v/opt:/opt:ro \
        -e 'LOGSPOUT=ignore' \
        -e "CONAN_PASSWORD=${CONAN_PASSWORD}" \
        "compilerexplorer/library-builder" \
        bash "${COMMAND}" "rust" "all" "all"
}

build_cpp_libraries

trap finish EXIT

build_rust_libraries

exit ${BUILD_FAILED}
