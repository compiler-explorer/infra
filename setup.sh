#!/bin/bash

set -ex

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

add-apt-repository -y ppa:chris-lea/node.js
add-apt-repository -y ppa:ubuntu-toolchain-r/test
apt-get -y update
apt-get -y upgrade
apt-get -y install $(cat ${DIR}/needs-installing)

cd /opt
wget http://downloads.dlang.org/releases/2014/dmd_2.065.0-0_amd64.deb
dpkg -i dmd_2.065.0-0_amd64.deb
rm dmd_2.065.0-0_amd64.deb

useradd gcc-user
mkdir /home/gcc-user
chown gcc-user /home/gcc-user
cd /home/gcc-user
su -c "git clone git://github.com/mattgodbolt/gcc-explorer.git" gcc-user
cd gcc-explorer
su -c "make prereqs" gcc-user

cp ${DIR}/nginx/* /etc/nginx/sites-available/
for config in $(ls -1 ${DIR}/nginx/*); do
    config=$(basename ${config})
    ln -sf /etc/nginx/sites-available/${config} /etc/nginx/sites-enabled/${config}
done

mkdir /var/cache/nginx-gcc
chown www-data /var/cache/nginx-gcc
mkdir /var/cache/nginx-sth
chown www-data /var/cache/nginx-sth

cd /home/ubuntu/
su -c "git clone git://github.com/mattgodbolt/jsbeeb.git" ubuntu

service nginx reload

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
s3cmd --config /root/.s3cfg get s3://gcc-explorer/opt/$f
tar zxf $f
rm $f
done

cp ${DIR}/gcc-explorer.conf /etc/init/
cp ${DIR}/d-explorer.conf /etc/init/

service gcc-explorer start
service d-explorer start

sleep 10

service nginx start
