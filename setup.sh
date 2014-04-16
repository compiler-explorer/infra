#!/bin/bash

set -ex

add-apt-repository -y ppa:chris-lea/node.js
add-apt-repository -y ppa:ubuntu-toolchain-r/test
apt-get -y update
apt-get -y upgrade
apt-get -y install $(cat needs-installing)

wget http://downloads.dlang.org/releases/2014/dmd_2.065.0-0_amd64.deb
dpkg -i dmd_2.065.0-0_amd64.deb

wget 'http://gdcproject.org/downloads/binaries/x86_64-linux-gnu/native_2.064.2_gcc4.8.2_665978132e_20140309.tar.xz'
cd /opt
tar Jxf ~/native_2.064.2_gcc4.8.2_665978132e_20140309.tar.xz

adduser --disabled-password gcc-user
cd /home/gcc-user
su -c "git clone git://github.com/mattgodbolt/gcc-explorer.git" gcc-user
cd gcc-explorer
su -c "make node_modules" gcc-user

mkdir /var/cache/nginx-gcc
chown www-data /var/cache/nginx-gcc
