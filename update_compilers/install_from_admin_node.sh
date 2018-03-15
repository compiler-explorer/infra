#!/bin/bash

set -ex

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd ${SCRIPT_DIR}

sudo ./install_binaries.sh
sudo ./install_compilers.sh nightly
sudo ./install_nonfree_compilers.sh
sudo ./install_libraries.sh
