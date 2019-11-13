#!/bin/bash

# This script installs all the free compilers from s3 into a dir in /opt.
# On EC2 this location is on an EFS drive.
ARG1="$1"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. ${SCRIPT_DIR}/common.inc ${ARG1}

echo "Starting installation at $(date), my pid $$"

CE_INSTALL_ARG=

if install_nightly; then
    echo "Installing nightly builds"
    CE_INSTALL_ARG=--enable=nightly
else
    echo "Skipping install of nightly compilers"
fi

ce_install() {
    "${SCRIPT_DIR}"/../bin/ce_install ${CE_INSTALL_ARG} install "$*"
}

#########################
# Rust
. ${SCRIPT_DIR}/install_rust_compilers.sh ${ARG1}

#########################
# Go
. ${SCRIPT_DIR}/install_go_compilers.sh ${ARG1}

#########################
# D
. ${SCRIPT_DIR}/install_d_compilers.sh ${ARG1}

#########################
# C++
ce_install 'compilers/c++'

#########################
# C
. ${SCRIPT_DIR}/install_c_compilers.sh ${ARG1}

#########################
# ISPC
. ${SCRIPT_DIR}/install_ispc_compilers.sh ${ARG1}

#########################
# Haskell
. ${SCRIPT_DIR}/install_haskell_compilers.sh ${ARG1}

#########################
# Swift
. ${SCRIPT_DIR}/install_swift_compilers.sh ${ARG1}

#########################
# Pascal
. ${SCRIPT_DIR}/install_pascal_compilers.sh ${ARG1}

#########################
# Assembly
. ${SCRIPT_DIR}/install_assembly_compilers.sh ${ARG1}

#########################
# Zig
. ${SCRIPT_DIR}/install_zig_compilers.sh ${ARG1}

#########################
# Clean
. ${SCRIPT_DIR}/install_clean_compilers.sh ${ARG1}

#########################
# Java
. ${SCRIPT_DIR}/install_java_compilers.sh ${ARG1}
