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
# TODO @rwarmstr suggests using just nvidia-headless-<version>-open for just
# the driver, IF we don't need CUDA installed systemwide. @mgodbolt wasn't
# sure what we actually need on the host.
CUDA_VERSION=12-8
apt install -y cuda-compiler-${CUDA_VERSION} cuda-runtime-${CUDA_VERSION}
