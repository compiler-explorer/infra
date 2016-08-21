#/bin/bash

set -e
mkdir -p /opt
cd /opt

getgdc() {
    vers=$1
    build=$2
    mkdir /opt/gdc${vers}
    pushd /opt/gdc${vers}
    curl -L ftp://ftp.gdcproject.org/binaries/${vers}/x86_64-linux-gnu/gdc-${vers}+${build}.tar.xz | tar Jxf -
    popd
}

getgdc 4.8.2 2.064.2
getgdc 4.9.3 2.066.1
getgdc 5.2.0 2.066.1

find -type f | xargs strip --strip-debug || true
