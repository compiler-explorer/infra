#!/bin/bash

set -exuo pipefail

# Run after a reboot, so the driver is loaded the way it will be on a real
# node rather than however the install left the running kernel.
apt-cache policy nvidia-modprobe
nvidia-smi

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
