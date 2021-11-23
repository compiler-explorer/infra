#!/bin/bash

set -exuo pipefail

finish() {
    ce builder stop
}
trap finish EXIT

ce builder status
ce builder start

BUILD_FAILED=0

build_libraries() {
    local IMAGE=$1
    local BUILD_NAME=library
    local COMMAND=build.sh

    local CONAN_PASSWORD
    CONAN_PASSWORD=$(aws ssm get-parameter --name /compiler-explorer/conanpwd | jq -r .Parameter.Value)

    ce builder exec -- sudo docker run --rm --name "${BUILD_NAME}.build" \
        -v/home/ubuntu/.s3cfg:/root/.s3cfg:ro \
        -v/opt:/opt:ro \
        -e 'LOGSPOUT=ignore' \
        -e "CONAN_PASSWORD=${CONAN_PASSWORD}" \
        "compilerexplorer/${IMAGE}-builder" \
        bash "${COMMAND}" "all" "all"
}

build_libraries library

exit ${BUILD_FAILED}
