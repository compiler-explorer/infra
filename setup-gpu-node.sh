#!/bin/bash

set -exuo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

bash "${DIR}/setup-node.sh"

# Empirically determined requirements
apt-get install -y libxml2 kmod "linux-headers-$(uname -r)"

pushd /tmp
curl -sL https://developer.download.nvidia.com/compute/cuda/12.6.1/local_installers/cuda_12.6.1_560.35.03_linux.run -o install.run
sh install.run --silent --driver
rm install.run
popd

# setup nvidia drivers https://docs.nvidia.com/cuda/cuda-installation-guide-linux/index.html#runfile-nouveau-ubuntu
echo -e "blacklist nouveau\noptions nouveau modeset=0\n" > /etc/modprobe.d/blacklist-nouveau.conf
update-initramfs -u

# script from https://docs.nvidia.com/cuda/cuda-installation-guide-linux/index.html#runfile-verifications
"${DIR}/setup-gpu-node-devices.sh"
