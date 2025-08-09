#!/bin/bash

set -exuo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

bash "${DIR}/setup-node.sh"

# On Ubuntu 22 the older system GCC won't compile the driver
. /etc/os-release
if [[ "$ID" == "ubuntu" ]] && [[ "${VERSION_ID%%.*}" -eq 22 ]]; then
    apt-get install -y gcc-12
    update-alternatives --install /usr/bin/gcc gcc /usr/bin/gcc-12 12
fi

pushd /tmp
curl -sL https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/cuda-keyring_1.1-1_all.deb -o cuda_keyring.deb
dpkg -i cuda_keyring.deb
rm cuda_keyring.deb
popd

apt-get -y update
# Note the hyphen in the CUDA version number, not a period.
DRIVER_VERSION=570
CUDA_VERSION=12-8
apt install -y \
    nvidia-headless-${DRIVER_VERSION}-open \
    nvidia-utils-${DRIVER_VERSION} \
    nvidia-driver-assistant \
    cuda-compiler-${CUDA_VERSION} \
    cuda-runtime-${CUDA_VERSION}

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
  if (deviceCount == 0) {
    printf("There are no available device(s) that support CUDA\n");
    exit(EXIT_FAILURE);
  } else {
    printf("Detected %d CUDA Capable device(s)\n", deviceCount);
  }
}
EOF
echo Compiling CUDA test...
/efs/compiler-explorer/cuda/12.6.2/bin/nvcc -o /tmp/cuda-test /tmp/cuda-test.cu
echo Running CUDA test...
/tmp/cuda-test
echo Done
