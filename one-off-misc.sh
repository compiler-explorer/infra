#!/bin/bash

SCRIPTNAME=$1
VERSION=$2
TMPNAME="misc_${SCRIPTNAME}_${VERSION}_$(date +%Y%m%d%H%M)"

showhelp() {
  echo "Usage ./one-off-misc.sh <scriptname> <version>"
}

if [[ "${SCRIPTNAME}" == "" ]]; then
  showhelp
  exit
fi

if [[ "${VERSION}" == "" ]]; then
  showhelp
  exit
fi

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
    if ! ce builder exec -- "$@" |& tee "${logdir}/log"; then
        BUILD_FAILED=1
        CE_BUILD_RESULT=FAILED
    else
        CE_BUILD_RESULT=OK
    fi

    local CE_BUILD_STATUS
    CE_BUILD_STATUS=$(grep -P "^ce-build-status:" "${logdir}/log" | cut -d ':' -f 2-)
    if [[ -z "${CE_BUILD_STATUS}" ]]; then
        CE_BUILD_STATUS=${CE_BUILD_RESULT}
    fi
    echo "${CE_BUILD_STATUS}" >"${logdir}/status"

    if [[ "${CE_BUILD_RESULT}" == "OK" ]]; then
        local REVISION
        REVISION=$(grep -P "^ce-build-revision:" "${logdir}/log" | cut -d ':' -f 2-)
        if [[ -n "${REVISION}" ]]; then
            echo "${REVISION}" >"${revisionfile}"
        fi
    fi

    if [[ "${CE_BUILD_STATUS}" == "OK" ]]; then
        date >"${logdir}/last_success"
    fi

    date >"${logdir}/end"
    set -e
}

build_misc() {
    local BUILD_NAME=$1
    local COMMAND=$2
    local BUILD=$3

    run_on_build "${BUILD_NAME}" /dev/null \
        sudo docker run --rm --name "${BUILD_NAME}.build" -v/home/ubuntu/.s3cfg:/home/gcc-user/.s3cfg:ro -e 'LOGSPOUT=ignore' \
        "compilerexplorer/misc-builder" \
        bash "${COMMAND}" "${BUILD}" s3://compiler-explorer/opt/
    log_to_json ${LOG_DIR} admin
}

build_misc ${TMPNAME} ${SCRIPTNAME} ${VERSION}

exit ${BUILD_FAILED}
