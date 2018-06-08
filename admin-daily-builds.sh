#!/bin/bash

set -exuo pipefail

finish() {
	ce builder stop
}
trap finish EXIT

ce builder status
ce builder start

BUILD_FAILED=0
run_on_build() {
    mkdir -p ~/build_logs
    local log=~/build_logs/$1
    shift
    set +e
	if ! ce builder exec -- "$@" 2>&1 | tee ${log}; then
	    BUILD_FAILED=1
    fi
	set -e
}

build_latest() {
    local IMAGE=$1
    local BUILD_NAME=$2
    shift 2
    run_on_build ${BUILD_NAME} \
      sudo docker run --rm --name ${BUILD_NAME}.build -v/home/ubuntu/.s3cfg:/root/.s3cfg:ro mattgodbolt/${IMAGE}-builder \
      bash "$@" trunk s3://compiler-explorer/opt/
}

build_latest gcc gcc build.sh
build_latest clang clang build.sh
build_latest clang clang_concepts build-concepts.sh
build_latest clang clang_cppx build-cppx.sh

exit ${BUILD_FAILED}
