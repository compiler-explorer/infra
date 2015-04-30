#/bin/bash

set -e
cd /opt

wget http://gdcproject.org/downloads/binaries/x86_64-linux-gnu/i686-linux-gnu_2.066.1_gcc4.9.2_f378f9ab41_20150405.tar.xz
tar Jxf i686-linux-gnu_2.066.1_gcc4.9.2_f378f9ab41_20150405.tar.xz
rm i686-linux-gnu_2.066.1_gcc4.9.2_f378f9ab41_20150405.tar.xz

wget http://gdcproject.org/downloads/binaries/x86_64-linux-gnu/x86_64-linux-gnu_2.066.1_gcc4.9.2_f378f9ab41_20150405.tar.xz
tar Jxf x86_64-linux-gnu_2.066.1_gcc4.9.2_f378f9ab41_20150405.tar.xz
rm x86_64-linux-gnu_2.066.1_gcc4.9.2_f378f9ab41_20150405.tar.xz
