#!/bin/bash

set -exuo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

"${DIR}/setup-node.sh"

# setup nvidia drivers https://docs.nvidia.com/cuda/cuda-installation-guide-linux/index.html#runfile-nouveau-ubuntu

pushd /tmp
wget https://developer.download.nvidia.com/compute/cuda/11.8.0/local_installers/cuda_11.8.0_520.61.05_linux.run
sh cuda_11.8.0_520.61.05_linux.run --silent --driver
popd

echo -e "blacklist nouveau\noptions nouveau modeset=0\n" > /etc/modprobe.d/blacklist-nouveau.conf
update-initramfs -u

# script from https://docs.nvidia.com/cuda/cuda-installation-guide-linux/index.html#runfile-verifications
./setup-gpu-node-devices.sh
