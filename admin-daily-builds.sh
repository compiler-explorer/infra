#!/bin/bash

set -exuo pipefail

finish() {
	ce builder stop
}
trap finish EXIT

ce builder status
ce builder start

FAILED=0
run_on_build() {
    set +e
	if ! ce builder exec "$@"; then
	    FAILED=1
    fi
	set -e
}

mkdir -p ~/build_logs
run_on_build sudo compiler-explorer-image/build_and_upload_latest_gcc.sh 2>&1 | tee ~/build_logs/gcc
run_on_build sudo compiler-explorer-image/build_and_upload_latest_clang.sh 2>&1 | tee ~/build_logs/clang
run_on_build sudo compiler-explorer-image/build_and_upload_latest_clang_concepts.sh 2>&1 | tee ~/build_logs/clang_concepts
run_on_build sudo compiler-explorer-image/build_and_upload_latest_clang_cppx.sh 2>&1 | tee ~/build_logs/clang_cppx
exit ${FAILED}
