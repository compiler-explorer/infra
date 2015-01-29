#/bin/bash

set -e
cd /opt

DMD_VERSION="2.065.0-0"
rm -f ${DMD_VERSION}_amd64.deb
wget http://downloads.dlang.org/releases/2014/dmd_${DMD_VERSION}_amd64.deb
dpkg -i dmd_${DMD_VERSION}_amd64.deb
rm dmd_${DMD_VERSION}_amd64.deb
