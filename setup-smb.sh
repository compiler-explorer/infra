#!/bin/bash

set -exuo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

env EXTRA_NFS_ARGS=",ro" "${DIR}/setup-common.sh"

apt-get -y update
apt-get -y install software-properties-common
apt-get install -y \
    gnutls-dev \
    liblmdb-dev \
    libgpgme-dev \
    libarchive-dev \
    libacl1-dev \
    libldap2-dev \
    libpopt-dev \
    libtasn1-bin

cpan App::cpanminus
cpanm Parse::Yapp
cpanm JSON

git clone https://github.com/samba-team/samba
cd samba
git checkout samba-4.17.7

./configure --prefix=/usr --enable-fhs "--bundled-libraries=cmocka,popt,NONE" "--bundled-libraries=talloc,pytalloc-util,tdb,pytdb,ldb,pyldb,pyldb-util,tevent,pytevent,popt" --without-pam --with-shared-modules='!vfs_snapper'
make

make install

cd ..

cp -f /infra/smb-server/smb.conf /etc/samba/smb.conf

mkdir -p /winshared
chown ubuntu:ubuntu /winshared

service smbd reload

# run rsync on startup
#/infra/smb-server/rsync-share.sh
