#!/bin/bash

set -e

curl -sL ftp://ftp.gnu.org/pub/gnu/binutils/binutils-2.21.1.tar.bz2 | tar jxf -
curl -sL ftp://ftp.gnu.org/pub/gnu/gcc/gcc-4.5.3/gcc-4.5.3.tar.bz2 | tar jxf -
curl -sL https://ftp.gnu.org/gnu/texinfo/texinfo-4.13a.tar.gz | tar zxf -
curl -sL http://www.mr511.de/software/libelf-0.8.13.tar.gz | tar zxf -

PREFIX=/opt/compiler-explorer/msp430/gcc-4.5.3

mkdir -p build/texinfo
pushd build/texinfo
../../texinfo-4.13/configure --prefix=/opt/texinfo
make -j$(proc)
make install
popd

export PATH=/opt/texinfo/bin:${PREFIX}/bin:${PATH}
&& make check && make install

( cd binutils-2.21.1 ; patch -p1 < ../msp430-binutils-2.21.1-20110716.patch )
mkdir -p build/binutils
pushd build/binutils
../../binutils-2.21.1/configure --target=msp430 --prefix=${PREFIX} CFLAGS='-O2 -g -Wno-error'
make -j$(nproc)
make install
popd

mkdir -p build/libelf
pushd build/libelf
../../libelf-0.8.13/configure --prefix=${PREFIX}
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
../../gcc-4.5.3/configure --target=msp430 --enable-languages=c,c++ --prefix=${PREFIX} --enable-long-long --disable-checking --disable-libssp --with-libelf=${PREFIX}
make -j$(nproc)
make install
popd
