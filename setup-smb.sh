#!/bin/bash

set -exuo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

env EXTRA_NFS_ARGS=",ro" "${DIR}/setup-common.sh"

apt-get -y update
apt-get -y install software-properties-common
apt-get install -y \
    samba-common \
    samba-common-bin \
    samba

cp -f /infra/smb-server/smb.conf /etc/samba/smb.conf

mkdir -p /winshared
chown ubuntu:ubuntu /winshared

service smbd reload

# run rsync on startup
/infra/smb-server/rsync-share.sh
