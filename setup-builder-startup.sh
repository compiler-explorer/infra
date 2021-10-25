#!/bin/bash

# called on every startup

set -euo pipefail

systemctl stop docker
umount /ephemeral || true
# swap was 57GB (!) hopefully we really don't need that much
SWAP_SIZE=$((8 * 1024 * 1024 * 1024 / 512))
sfdisk /dev/nvme1n1 <<EOF
,${SWAP_SIZE},82
;
EOF
sync
sleep 2 # let the device get registered
mkswap /dev/nvme1n1p1
swapon /dev/nvme1n1p1
mkfs.ext4 -F /dev/nvme1n1p2
rm -rf /ephemeral
mkdir /ephemeral
mount /dev/nvme1n1p2 /ephemeral

cat >/etc/docker/daemon.json <<EOF
{
        "data-root": "/ephemeral/docker"
}
EOF

mount_opt() {
  mkdir -p /opt/compiler-explorer
  mountpoint /opt/compiler-explorer || mount --bind /efs/compiler-explorer /opt/compiler-explorer

  mkdir -p /opt/intel
  mountpoint /opt/intel || mount --bind /efs/intel /opt/intel

  mkdir -p /opt/arm
  mountpoint /opt/arm || mount --bind /efs/arm /opt/arm

  [ -f /opt/.health ] || touch /opt/.health
  mountpoint /opt/.health || mount --bind /efs/.health /opt/.health

  ./mount-all-img.sh
}

mount_opt

systemctl start docker
