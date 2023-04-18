#!/bin/bash

set -exuo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

env EXTRA_NFS_ARGS=",ro" "${DIR}/setup-common.sh"

apt-get -y update
apt-get -y install software-properties-common
apt-get install -y \
    pkg-config \
    gcc-10 \
    automake \
    flex \
    bison \
    gnutls-dev \
    liblmdb-dev \
    libgpgme-dev \
    libarchive-dev \
    libacl1-dev \
    libldap2-dev \
    libpopt-dev \
    libtasn1-bin \
    libjansson-dev \
    python3-markdown \
    python3-dnspython

cpan App::cpanminus
cpanm Parse::Yapp
cpanm JSON

git clone --depth 1 --branch samba-4.17.7 https://github.com/samba-team/samba
cd samba

./configure --enable-fhs --systemd-install-services "--bundled-libraries=cmocka,popt,NONE" "--bundled-libraries=talloc,pytalloc-util,tdb,pytdb,ldb,pyldb,pyldb-util,tevent,pytevent,popt" --without-pam --with-shared-modules='!vfs_snapper'
make

make install

cd ..

cp /usr/local/samba/lib/systemd/system/* /etc/systemd/system/

cp -f /infra/smb-server/smb.conf /usr/local/samba/etc/samba/smb.conf

mkdir -p /winshared
chown ubuntu:ubuntu /winshared

systemctl enable smb

service smbd start

# run rsync on startup
#/infra/smb-server/rsync-share.sh
