#!/bin/bash

set -ex

add-apt-repository -y ppa:chris-lea/node.js
#add-apt-repository -y ppa:ubuntu-toolchain-r/test
apt-get -y update
#apt-get -y upgrade
apt-get -y install $(cat needs-installing)
#adduser --disabled-password gcc-user
cd /home/gcc-user
#su -c "git clone git://github.com/mattgodbolt/gcc-explorer.git" gcc-user
cd gcc-explorer
su -c "make node_modules" gcc-user
