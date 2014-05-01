#!/bin/bash

set -ex

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

get_version() {
    (dpkg -s $1 2>/dev/null|| echo 'Version: none') | grep '^Version' | cut -f2 -d\ 
}

get_or_update_repo() {
    local USER=$1
    local REPO=$2
    if [[ ! -e ${REPO} ]]; then
        su -c "git clone git://github.com/mattgodbolt/${REPO}.git" "${USER}"
    else
        su -c "cd ${REPO}; git pull" "${USER}"
    fi
}

service nginx stop || true
service gcc-explorer stop || true
service d-explorer stop || true

add-apt-repository -y ppa:chris-lea/node.js
add-apt-repository -y ppa:ubuntu-toolchain-r/test
apt-get -y update
apt-get -y upgrade --force-yes
apt-get -y install $(cat ${DIR}/needs-installing)

cd /opt
DMD_VERSION="2.065.0-0"
if [[ "$(get_version dmd)" != "${DMD_VERSION}" ]]; then
    wget http://downloads.dlang.org/releases/2014/dmd_${DMD_VERSION}_amd64.deb
    dpkg -i ${DMD_VERSION}_amd64.deb
    rm ${DMD_VERSION}_amd64.deb
fi

if ! grep gcc-user /etc/passwd; then
    useradd gcc-user
    mkdir /home/gcc-user
    chown gcc-user /home/gcc-user
fi

cd /home/gcc-user
get_or_update_repo gcc-user gcc-explorer
cd gcc-explorer
su -c "make prereqs" gcc-user

cp ${DIR}/nginx/* /etc/nginx/sites-available/
for config in $(ls -1 ${DIR}/nginx/*); do
    config=$(basename ${config})
    ln -sf /etc/nginx/sites-available/${config} /etc/nginx/sites-enabled/${config}
done

mkdir -p /var/cache/nginx-gcc
chown www-data /var/cache/nginx-gcc
mkdir -p /var/cache/nginx-sth
chown www-data /var/cache/nginx-sth

cd /home/ubuntu/
get_or_update_repo ubuntu jsbeeb

cat > /root/.s3cfg <<EOF
[default]
access_key = ${S3_ACCESS_KEY}
secret_key = ${S3_SECRET_KEY}
EOF

cd /opt
for f in clang-3.2.tar.gz \
    clang-3.3.tar.gz \
    gcc-4.9.0-0909-concepts.tar.gz \
    gcc-4.9.0-with-concepts.tar.gz \
    intel.tar.gz \
    ; do
if [[ ! -e "$f.installed" ]]; then
    rm -f $f.installed
    s3cmd --config /root/.s3cfg get s3://gcc-explorer/opt/$f
    tar zxf $f
    rm $f
    touch "$f.installed"
fi
done

# Unconditionally install the nightly rust
cd /opt
curl http://static.rust-lang.org/dist/rust-nightly-x86_64-unknown-linux-gnu.tar.gz | tar zxf -
cd rust-nightly-x86_64-unknown-linux-gnu
./install.sh --prefix=/opt/rust-nightly

cp ${DIR}/gcc-explorer.conf /etc/init/
cp ${DIR}/d-explorer.conf /etc/init/

service gcc-explorer start
service d-explorer start

sleep 10

service nginx start
