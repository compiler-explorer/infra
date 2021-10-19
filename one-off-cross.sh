#!/bin/bash

REPO=$1
SCRIPTNAME=$2
ARCHITECTURE=$3
VERSION=$4
BASEVERSION=$5
TMPNAME="${REPO}_$(date +%Y%m%d%H%M)"

showhelp() {
  echo "Usage ./one-off-cross.sh <reponame> build.sh <architecture> <version> <baseversion>"
}

if [[ "${REPO}" == "" ]]; then
  showhelp
  exit
fi

if [[ "${SCRIPTNAME}" == "" ]]; then
  showhelp
  exit
fi

if [[ "${ARCHITECTURE}" == "" ]]; then
  showhelp
  exit
fi

if [[ "${VERSION}" == "" ]]; then
  showhelp
  exit
fi

if [[ "${BASEVERSION}" == "" ]]; then
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

build_latest_cross() {
    local IMAGE=$1
    local BUILD_NAME=$2
    local COMMAND=$3
    local ARCH=$4
    local BUILD=$5

    # We don't support the "revision" for cross compilers. I looked briefly at adding it
    # using `ct-ng sources` and similar magic, but the number of dependencies (e.g. linux source, gcc trunk)
    # means we'll almost certainly be different every time anyway.
    run_on_build "${BUILD_NAME}" /dev/null \
        sudo docker run --rm --name "${BUILD_NAME}.build" -v/home/ubuntu/.s3cfg:/home/gcc-user/.s3cfg:ro -e 'LOGSPOUT=ignore' \
        "compilerexplorer/${IMAGE}-cross-builder" \
        bash "${COMMAND}" "${ARCH}" "${BUILD}" s3://compiler-explorer/opt/
    log_to_json ${LOG_DIR} admin
}

build_latest_cross ${REPO} ${TMPNAME} ${SCRIPTNAME} ${ARCHITECTURE} ${VERSION} ${BASEVERSION}

exit ${BUILD_FAILED}
