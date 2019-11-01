#!/bin/bash

# called on every startup

set -ex

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

systemctl stop docker
umount /ephemeral || true
sfdisk -f /dev/nvme0n1 <<EOF
label: dos
label-id: 0xbebcaa2e
device: /dev/nvme0n1
unit: sectors

/dev/nvme0n1p1 : start=        2048, size=   781247952, type=83
EOF
sync
sleep 2 # let the device get registered
mkfs.ext4 -F /dev/nvme0n1p1
rm -rf /ephemeral
mkdir /ephemeral
mount /dev/nvme0n1p1 /ephemeral

cat >/etc/docker/daemon.json <<EOF
{
        "data-root": "/ephemeral/docker"
}
EOF

systemctl start docker
