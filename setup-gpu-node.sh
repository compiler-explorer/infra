#!/bin/bash

set -exuo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

bash "${DIR}/setup-node.sh"

pushd /tmp
curl -sL https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/cuda-keyring_1.1-1_all.deb -o cuda_keyring.deb
dpkg -i cuda_keyring.deb
rm cuda_keyring.deb
popd

apt-get -y update
# The CUDA packages include the most appropriate driver for its version.
# Note the hyphen in the version number, not a period.
CUDA_VERSION=12-8
apt install -y nvidia-headless-570-open nvidia-utils-570 nvidia-driver-assistant cuda-compiler-${CUDA_VERSION} cuda-runtime-${CUDA_VERSION}
