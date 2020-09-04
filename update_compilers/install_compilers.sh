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
ce_install 'compilers/rust'

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
# Haskell
ce_install 'compilers/haskell'

#########################
# Swift
ce_install 'compilers/swift'

#########################
# Pascal
ce_install 'compilers/pascal'

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
ce_install 'compilers/java'

#########################
# Circle
ce_install 'compilers/circle'

#########################
# Nim
ce_install 'compilers/nim'

#########################
# Python
ce_install 'compilers/python'
