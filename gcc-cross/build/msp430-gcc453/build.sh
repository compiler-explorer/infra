#!/bin/bash

cd "$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
set -e

curl -sL ftp://ftp.gnu.org/pub/gnu/binutils/binutils-2.21.1.tar.bz2 | tar jxf -
curl -sL ftp://ftp.gnu.org/pub/gnu/gcc/gcc-4.5.3/gcc-4.5.3.tar.bz2 | tar jxf -
curl -sL https://ftp.gnu.org/gnu/texinfo/texinfo-4.13a.tar.gz | tar zxf -
curl -sL http://www.mr511.de/software/libelf-0.8.13.tar.gz | tar zxf -

OUTPUT=/home/gcc-user/msp430-gcc-4.5.3.tar.xz
STAGING_DIR=/opt/compiler-explorer/msp430/gcc-4.5.3

S3OUTPUT=""
if echo $1 | grep s3://; then
    S3OUTPUT=$1
else
    OUTPUT=${1-/home/gcc-user/msp430-gcc-4.5.3.tar.xz}
fi

mkdir -p build/texinfo
pushd build/texinfo
../../texinfo-4.13/configure --prefix=/opt/texinfo
make -j$(proc)
make install
popd

export PATH=/opt/texinfo/bin:${STAGING_DIR}/bin:${PATH}

( cd binutils-2.21.1 ; patch -p1 < ../msp430-binutils-2.21.1-20110716.patch )
mkdir -p build/binutils
pushd build/binutils
../../binutils-2.21.1/configure --target=msp430 --prefix=${STAGING_DIR} CFLAGS='-O2 -g -Wno-error'
make -j$(nproc)
make install
popd

mkdir -p build/libelf
pushd build/libelf
../../libelf-0.8.13/configure --prefix=${STAGING_DIR}
make -j$(nproc)
make install
popd

pushd gcc-4.5.3
patch -p1 < ../../patches/gcc/4.5.4/999-inline.patch
patch -p1 < ../msp430-gcc-4.5.3-20110706.patch
../download_prerequisites
popd
mkdir -p build/gcc
pushd build/gcc
../../gcc-4.5.3/configure --target=msp430 --enable-languages=c,c++ --prefix=${STAGING_DIR} --enable-long-long --disable-checking --disable-libssp --with-libelf=${PREFIX}
make -j$(nproc)
make install
popd

# Compress all the images with upx
for EXE in $(find ${STAGING_DIR} -type f -executable -not -regex '.*\.so.*'); do
    upx ${EXE} || true
done

tar Jcf ${OUTPUT} -C ${STAGING_DIR}/.. gcc-4.5.3

if [[ ! -z "${S3OUTPUT}" ]]; then
    s3cmd put --rr ${OUTPUT} ${S3OUTPUT}
fi
