#!/bin/bash

set -ex

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

add-apt-repository -y ppa:chris-lea/node.js
add-apt-repository -y ppa:ubuntu-toolchain-r/test
apt-get -y update
apt-get -y upgrade
apt-get -y install $(cat ${DIR}/needs-installing)

rmdir /opt
ln -sf /mnt /opt
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
su -c "make node_modules" gcc-user

mkdir /var/cache/nginx-gcc
chown www-data /var/cache/nginx-gcc

cp ${DIR}/nginx-conf /etc/nginx/sites-available/default
service nginx reload

cat > ~/.s3cfg <<EOF
[default]
access_key = ${S3_ACCESS_KEY}
secret_key = ${S3_SECRET_KEY}
EOF

for f in clang-3.2.tar.gz \
    clang-3.3.tar.gz \
    gcc-4.9.0-0909-concepts.tar.gz \
    gcc-4.9.0-with-concepts.tar.gz \
    intel.tar.gz \
    ; do
s3cmd get s3://gcc-explorer/opt/$f
tar zxf $f
rm $f
done

# Intel compiler
#s3cmd get s3://gcc-explorer/opt/l_ccompxe_2013.1.117.tar.xz
#tar Jxf l_ccompxe_2013.1.117.tar.xz
#rm l_ccompxe_2013.1.117.tar.xz
#cat > /tmp/install.sh <<EOF
#SEND_USAGE_DATA=no
#PSET_SERIAL_NUMBER=${INTEL_SERIAL_NUMBER}
#ACTIVATION=serial_number
#CONTINUE_WITH_INSTALLDIR_OVERWRITE=yes
#CONTINUE_WITH_OPTIONAL_ERROR=yes
#PSET_INSTALL_DIR=/opt/intel/composer_xe_2013.1.117
#INSTALL_MODE=NONRPM
#ACCEPT_EULA=accept
#EOF
#cd l_ccompxe_2013.1.117
#./install.sh --silent /tmp/install.sh
#cd ..
#rm -rf l_ccompxe_2013.1.117

cp ${DIR}/gcc-explorer.conf /etc/init/
cp ${DIR}/d-explorer.conf /etc/init/

service gcc-explorer start
service d-explorer start

sleep 10

service nginx start
