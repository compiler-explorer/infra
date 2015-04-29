#/bin/bash

set -e
cd /opt

wget http://gdcproject.org/downloads/binaries/x86_64-linux-gnu/i686-linux-gnu_2.066.1_gcc4.9.2_f378f9ab41_20150405.tar.xz
tar Jxf i686-linux-gnu_2.066.1_gcc4.9.2_f378f9ab41_20150405.tar.xz
rm i686-linux-gnu_2.066.1_gcc4.9.2_f378f9ab41_20150405.tar.xz

DMD_VERSION="2.066.1-0"
rm -f ${DMD_VERSION}_amd64.deb
wget http://downloads.dlang.org/releases/2014/dmd_${DMD_VERSION}_amd64.deb
dpkg -i dmd_${DMD_VERSION}_amd64.deb
rm dmd_${DMD_VERSION}_amd64.deb
