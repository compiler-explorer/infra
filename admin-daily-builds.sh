#!/bin/bash

set -ex

finish() {
	ce builder stop
}
trap finish EXIT

ce builder status
ce builder start


FAILED=0
run_on_build() {
	ce builder exec $* || FAILED=1
}

mkdir -p ~/build_logs
run_on_build sudo compiler-explorer-image/build_and_upload_latest_gcc.sh | tee ~/build_logs/gcc
run_on_build sudo compiler-explorer-image/build_and_upload_latest_clang.sh | tee ~/build_logs/clang
run_on_build sudo compiler-explorer-image/build_and_upload_latest_clang_concepts.sh | tee ~/build_logs/clang_concepts
run_on_build sudo compiler-explorer-image/build_and_upload_latest_clang_cppx.sh | tee ~/build_logs/clang_cppx

exit $FAILED
