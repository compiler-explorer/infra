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
	if ! ce builder exec "$@" 2>&1 | tee ${log}; then
	    BUILD_FAILED=1
    fi
	set -e
}

run_on_build gcc sudo compiler-explorer-image/build_and_upload_latest_gcc.sh
run_on_build clang sudo compiler-explorer-image/build_and_upload_latest_clang.sh
run_on_build clang_concepts sudo compiler-explorer-image/build_and_upload_latest_clang_concepts.sh
run_on_build clang_cppx sudo compiler-explorer-image/build_and_upload_latest_clang_cppx.sh

exit ${BUILD_FAILED}
