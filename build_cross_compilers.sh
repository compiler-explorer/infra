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
    local ARCH=$1
    local VERSION=$2
    shift 2
    local OUTPUT=s3://compiler-explorer/opt/${ARCH}-gcc-${VERSION}.tar.xz
    if aws s3 ls ${OUTPUT}; then
        echo "File ${OUTPUT} exists, skipping"
        return
    fi

    run_on_build gcc-cross \
      sudo docker run --rm --name gcc-cross.build -v/home/ubuntu/.s3cfg:/home/gcc-user/.s3cfg:ro mattgodbolt/gcc-cross \
      bash ./build.sh ${VERSION} s3://compiler-explorer/opt/
}


build_cross powerpc64le at12

exit ${BUILD_FAILED}
