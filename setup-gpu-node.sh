#!/bin/bash

set -exuo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

pushd /tmp
curl -sL https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/cuda-keyring_1.1-1_all.deb -o cuda_keyring.deb
dpkg -i cuda_keyring.deb
rm cuda_keyring.deb
popd

apt-get -y update
# Note the hyphen in the CUDA version number, not a period.
DRIVER_VERSION=570
CUDA_VERSION=12-8
apt install -y nvidia-headless-${DRIVER_VERSION}-open nvidia-utils-${DRIVER_VERSION} nvidia-driver-assistant cuda-compiler-${CUDA_VERSION} cuda-runtime-${CUDA_VERSION}

# Ensure the above worked.
cat <<EOF > /tmp/cuda-test.cu
#include <cstdio>

int main () {
  int deviceCount = 0;
  cudaError_t error_id = cudaGetDeviceCount(&deviceCount);

  if (error_id != cudaSuccess) {
    printf("cudaGetDeviceCount returned %d\n-> %s\n",
           static_cast<int>(error_id), cudaGetErrorString(error_id));
    printf("Result = FAIL\n");
    exit(EXIT_FAILURE);
  }

}
EOF
nvcc -o /tmp/cuda-test /tmp/cuda-test.cu
/tmp/cuda-test

bash "${DIR}/setup-node.sh"
