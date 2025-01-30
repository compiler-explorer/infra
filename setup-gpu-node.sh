#!/bin/bash

set -exuo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

bash "${DIR}/setup-node.sh"

# Empirically determined requirements
apt-get install -y libxml2 kmod "linux-headers-$(uname -r)"

pushd /tmp
curl -sL https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/cuda-keyring_1.1-1_all.deb -o cuda_keyring.deb
dpkg -i cuda_keyring.deb
rm cuda_keyring.deb
apt-get -y update
# The driver version is nvidia-open-*
# The CUDA version is cuda-*
apt install -y nvidia-open-570 cuda-12-8
popd
