#!/bin/bash

mkdir -p /opt/compiler-explorer/buildrevs

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
    local GITURL=$5
    local GITBRANCH=$6
    local SHOULDBUILD=0
    local LATESTREV="Unknown"
    local FILEWITHHASH="/opt/compiler-explorer/buildrevs/${IMAGE}-${BUILD}.txt"

    if [[ "${GITURL}" != "" ]]; then
        LATESTREV=$(git ls-remote --heads ${GITURL} ${GITBRANCH})
        BUILTREV=""
        if [ -f "${FILEWITHHASH}" ]; then
            BUILTREV=$(cat ${FILEWITHHASH})
        fi

        if [ "${BUILTREV}" != "${LATESTREV}" ]; then
            SHOULDBUILD=1
        fi
    else
        SHOULDBUILD=1
    fi

    if [ $SHOULDBUILD -eq 1 ]; then
        echo "Starting build ${BUILD_NAME}"

        run_on_build "${BUILD_NAME}" \
            sudo docker run --rm --name "${BUILD_NAME}.build" -v/home/ubuntu/.s3cfg:/root/.s3cfg:ro -e 'LOGSPOUT=ignore' \
            "compilerexplorer/${IMAGE}-builder" \
            bash "${COMMAND}" "${BUILD}" s3://compiler-explorer/opt/
        log_to_json ${LOG_DIR} admin
        
        if [[ ${BUILD_FAILED} -eq 0 ]]; then
            echo "Writing hash to file"
            echo "${LATESTREV}" > ${FILEWITHHASH}
        fi
    fi
}

# llvm build is fast, so lets do it first
build_latest clang llvm build-llvm.sh trunk https://github.com/llvm/llvm-project.git master

build_latest gcc gcc build.sh trunk git://gcc.gnu.org/git/gcc.git master
build_latest gcc gcc_contracts build.sh lock3-contracts-trunk https://gitlab.com/lock3/gcc-new.git contracts
build_latest gcc gcc_modules build.sh cxx-modules-trunk git://gcc.gnu.org/git/gcc.git devel/c++-modules
build_latest gcc gcc_coroutines build.sh cxx-coroutines-trunk git://gcc.gnu.org/git/gcc.git devel/c++-coroutines
build_latest gcc gcc_embed build.sh embed-trunk https://github.com/ThePhD/gcc.git feature/embed
build_latest gcc gcc_static_analysis build.sh static-analysis-trunk git://gcc.gnu.org/git/gcc.git devel/analyzer
build_latest clang clang build.sh trunk https://github.com/llvm/llvm-project.git master

# gitlab doesn't support ls-remote without logging in apparantly
build_latest clang clang_cppx build-cppx.sh trunk "" ""

build_latest clang clang_relocatable build-relocatable.sh trunk https://github.com/Quuxplusone/llvm-project.git trivially-relocatable
build_latest clang clang_autonsdmi build-autonsdmi.sh trunk https://github.com/cor3ntin/llvm-project experiments
build_latest clang clang_lifetime build-lifetime.sh trunk https://github.com/mgehre/llvm-project lifetime

# no idea how this works
build_latest clang clang_parmexpr build-parmexpr.sh trunk "" ""

build_latest clang clang_embed build-embed.sh embed-trunk https://github.com/ThePhD/llvm-project.git feature/embed
build_latest go go build.sh trunk https://go.googlesource.com/go master

exit ${BUILD_FAILED}
