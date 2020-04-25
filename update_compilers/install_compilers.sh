#!/bin/bash

# This script installs all the free compilers from s3 into a dir in /opt.
# On EC2 this location is on an EFS drive.
ARG1="$1"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.inc
. "${SCRIPT_DIR}/common.inc" "${ARG1}"

echo "Starting installation at $(date), my pid $$"

if install_nightly; then
    echo "Installing nightly builds"
else
    echo "Skipping install of nightly compilers"
fi

#########################
# Rust
# shellcheck source=install_rust_compilers.sh
. "${SCRIPT_DIR}"/install_rust_compilers.sh "${ARG1}"

#########################
# Go
ce_install 'compilers/go'

#########################
# D
# shellcheck source=install_d_compilers.sh
. "${SCRIPT_DIR}"/install_d_compilers.sh "${ARG1}"

#########################
# C++
ce_install 'compilers/c++'

#########################
# C
ce_install 'compilers/c'

#########################
# ISPC
ce_install 'compilers/ispc'

#########################
# Haskell
# shellcheck source=install_d_compilers.sh
. "${SCRIPT_DIR}"/install_haskell_compilers.sh "${ARG1}"

#########################
# Swift
# shellcheck source=install_swift_compilers.sh
. "${SCRIPT_DIR}"/install_swift_compilers.sh "${ARG1}"

#########################
# Pascal
# shellcheck source=install_pascal_compilers.sh
. "${SCRIPT_DIR}"/install_pascal_compilers.sh "${ARG1}"

#########################
# Assembly
# shellcheck source=install_assembly_compilers.sh
. "${SCRIPT_DIR}"/install_assembly_compilers.sh "${ARG1}"

#########################
# Zig
# shellcheck source=install_zig_compilers.sh
. "${SCRIPT_DIR}"/install_zig_compilers.sh "${ARG1}"

#########################
# Clean
# shellcheck source=install_clean_compilers.sh
. "${SCRIPT_DIR}"/install_clean_compilers.sh "${ARG1}"

#########################
# Java
# shellcheck source=install_java_compilers.sh
. "${SCRIPT_DIR}"/install_java_compilers.sh "${ARG1}"

#########################
# Circle
ce_install 'compilers/circle'

#########################
# Nim
# shellcheck source=install_nim_compilers.sh
. "${SCRIPT_DIR}"/install_nim_compilers.sh ${ARG1}

#########################
# Python
ce_install 'compilers/python'
