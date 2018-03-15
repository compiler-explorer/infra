#!/bin/bash

set -ex

sudo ./install_binaries.sh
sudo ./install_compilers.sh nightly
sudo ./install_nonfree_compilers.sh
sudo ./install_libraries.sh
