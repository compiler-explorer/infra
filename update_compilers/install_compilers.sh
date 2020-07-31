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
ce_install 'compilers/d'

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
# Haskelllanguage
# shellcheck source=install_haskell_compilers.sh
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
ce_install 'compilers/asm'

#########################
# Zig
ce_install 'compilers/zig'

#########################
# Clean
ce_install 'compilers/clean'

#########################
# Java
# shellcheck source=install_java_compilers.sh
. "${SCRIPT_DIR}"/install_java_compilers.sh "${ARG1}"

#########################
# Circle
ce_install 'compilers/circle'

#########################
# Nim
ce_install 'compilers/nim'

#########################
# Python
ce_install 'compilers/python'
