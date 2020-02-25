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
    mkdir -p "${logdir}"
    shift
    set +e
    date >"${logdir}/begin"
    if ! ce builder exec -- "$@" |& tee ${logdir}/log; then
        BUILD_FAILED=1
        echo FAILED >${logdir}/status
    else
        echo OK >${logdir}/status
    fi
    date >${logdir}/end
    set -e
}

build_latest() {
    local IMAGE=$1
    local BUILD_NAME=$2
    local COMMAND=$3
    local BUILD=$4
    run_on_build "${BUILD_NAME}" \
        sudo docker run --rm --name "${BUILD_NAME}.build" -v/home/ubuntu/.s3cfg:/root/.s3cfg:ro -e 'LOGSPOUT=ignore' \
        "compilerexplorer/${IMAGE}-builder" \
        bash "${COMMAND}" "${BUILD}" s3://compiler-explorer/opt/
    log_to_json ${LOG_DIR} admin
}

# llvm build is fast, so lets do it first
build_latest clang llvm build-llvm.sh trunk

build_latest gcc gcc build.sh trunk
build_latest gcc gcc_contracts build.sh lock3-contracts-trunk
build_latest gcc gcc_modules build.sh cxx-modules-trunk
build_latest gcc gcc_coroutines build.sh cxx-coroutines-trunk
build_latest gcc gcc_embed build.sh embed-trunk
build_latest gcc gcc_static_analysis build.sh static-analysis-trunk
build_latest clang clang build.sh trunk
build_latest clang clang_concepts build-concepts.sh trunk
build_latest clang clang_cppx build-cppx.sh trunk
build_latest clang clang_relocatable build-relocatable.sh trunk
build_latest clang clang_autonsdmi build-autonsdmi.sh trunk
build_latest clang clang_lifetime build-lifetime.sh trunk
build_latest clang clang_parmexpr build-parmexpr.sh trunk
build_latest clang clang_embed build-embed.sh embed-trunk
build_latest go go build.sh trunk

exit ${BUILD_FAILED}
