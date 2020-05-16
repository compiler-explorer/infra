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
    local revisionfile=$2
    mkdir -p "${logdir}"
    shift 2
    set +e
    date >"${logdir}/begin"
    local CE_BUILD_RESULT=""
    if ! ce builder exec -- "$@" |& tee ${logdir}/log; then
        BUILD_FAILED=1
        CE_BUILD_RESULT=FAILED
    else
        CE_BUILD_RESULT=OK
    fi

    local CE_BUILD_STATUS=$(grep -P "^ce-build-status:" "${logdir}/log" | cut -d ':' -f 2-)
    if [[ -z "${CE_BUILD_STATUS}" ]]; then
        CE_BUILD_STATUS=${CE_BUILD_RESULT}
    fi
    echo "${CE_BUILD_STATUS}" >${logdir}/status

    if [[ "${CE_BUILD_RESULT}" == "OK" ]]; then
        local REVISION=$(grep -P "^ce-build-revision:" "${LOG_DIR}/${IMAGE}/log" | cut -d ':' -f 2-)
        if [[ ! -z "${REVISION}" ]]; then
            echo "${REVISION}" > "${revisionfile}"
        fi
        date >${logdir}/last_success
    fi
    date >${logdir}/end
    set -e
}

build_latest() {
    local IMAGE=$1
    local BUILD_NAME=$2
    local COMMAND=$3
    local BUILD=$4

    local REVISION_FILENAME=/opt/.buildrevs/${BUILD_NAME}
    local REVISION=""

    if [[ -f "${REVISION_FILENAME}" ]]; then
        REVISION=$(cat "${REVISION_FILENAME}")
    fi

    run_on_build "${BUILD_NAME}" "${REVISION_FILENAME}" \
        sudo docker run --rm --name "${BUILD_NAME}.build" -v/home/ubuntu/.s3cfg:/root/.s3cfg:ro -e 'LOGSPOUT=ignore' \
        "compilerexplorer/${IMAGE}-builder" \
        bash "${COMMAND}" "${BUILD}" s3://compiler-explorer/opt/ "${REVISION}"
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
build_latest clang clang_cppx build-cppx.sh trunk
build_latest clang clang_relocatable build-relocatable.sh trunk
build_latest clang clang_autonsdmi build-autonsdmi.sh trunk
build_latest clang clang_lifetime build-lifetime.sh trunk
build_latest clang clang_parmexpr build-parmexpr.sh trunk
build_latest clang clang_embed build-embed.sh embed-trunk
build_latest go go build.sh trunk

exit ${BUILD_FAILED}
