#!/bin/bash

set -exuo pipefail

finish() {
	ce builder stop
}
trap finish EXIT

ce builder status
ce builder start

LOG_DIR=~/build_logs
BUILD_FAILED=0
run_on_build() {
    local logdir=${LOG_DIR}/$1
    mkdir -p ${logdir}
    shift
    set +e
    date > ${logdir}/begin
    if ! ce builder exec -- "$@" 2>&1 | tee ${logdir}/log; then
        BUILD_FAILED=1
        echo FAILED > ${logdir}/status
    else
        echo OK > ${logdir}/status
    fi
    date > ${logdir}/end
    set -e
}

build_cross() {
    local IMAGE=$1
    local BUILD_NAME=$2
    shift 2
    run_on_build ${BUILD_NAME} \
      sudo docker run --rm --name ${BUILD_NAME}.build -v/home/ubuntu/.s3cfg:/root/.s3cfg:ro mattgodbolt/${IMAGE} \
      bash "$@" trunk s3://compiler-explorer/opt/
    log_to_json ${LOG_DIR} admin/buildStatus.json
}

build_cross gcc-cross gcc build.sh arm 8.2.0
build_cross gcc-cross gcc build.sh arm 7.3.0
build_cross gcc-cross gcc build.sh arm 6.4.0
build_cross gcc-cross gcc build.sh arm64 8.2.0
build_cross gcc-cross gcc build.sh arm64 7.3.0
build_cross gcc-cross gcc build.sh arm64 6.4.0

exit ${BUILD_FAILED}
