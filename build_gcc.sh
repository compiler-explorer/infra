#!/bin/bash

set -e

VERSION=$1
shift

ROOT=$(pwd)
rm -rf /tmp/gcc-build
mkdir -p /tmp/gcc-build
cd /tmp/gcc-build

# Workaround for Ubuntu builds
export LIBRARY_PATH=/usr/lib/x86_64-linux-gnu
BUILD_DIR=$(pwd)/build
STAGING_DIR=$(pwd)/staging
mkdir -p ${STAGING_DIR}

echo "Fetching GCC"
if echo ${VERSION} | grep 'snapshot-'; then
    VERSION=${VERSION/#snapshot-/}
    wget ftp://gcc.gnu.org/pub/gcc/snapshots/${VERSION}/gcc-${VERSION}.tar.bz2
else
    wget ftp://ftp.gnu.org/gnu/gcc/gcc-${VERSION}/gcc-${VERSION}.tar.bz2
fi
echo "Extracting GCC..."
tar jxf gcc-${VERSION}.tar.bz2

BINUTILS_VERSION=2.24
echo "Fetching binutils ${BINUTILS_VERSION}"
wget http://ftp.gnu.org/gnu/binutils/binutils-${BINUTILS_VERSION}.tar.bz2
tar jxf binutils-${BINUTILS_VERSION}.tar.bz2
BINUTILS_DIR=binutils-${BINUTILS_VERSION}
BINUTILS_FILES=$(cd ${BINUTILS_DIR}; ls -1)
pushd gcc-${VERSION}
for file in ${BINUTILS_FILES}
do 
    if [ ! -e "$file" ]
    then
        ln -sf "../${BINUTILS_DIR}/${file}"
    fi
done
popd

LIBELF_VERSION=0.8.13
echo "Fetching and building Libelf ${LIBELF_VERSION}"
LIBELF_DIR=${BUILD_DIR}/libelf-${LIBELF_VERSION}
wget http://www.mr511.de/software/libelf-${LIBELF_VERSION}.tar.gz
tar zxf libelf-${LIBELF_VERSION}.tar.gz
pushd libelf-${LIBELF_VERSION}
./configure --prefix=${LIBELF_DIR}
make -j1 install
popd
DEP_CONFIG+=" --with-libelf=${LIBELF_DIR}"
LD_LIBRARY_PATH+=":${LIBELF_DIR}/lib"

echo "Downloading prerequisites"
pushd gcc-${VERSION}
./contrib/download_prerequisites
popd

CONFIG=""
CONFIG+=" --build=x86_64-linux-gnu"
CONFIG+=" --disable-multilibs"
CONFIG+=" --enable-clocale=gnu"
CONFIG+=" --enable-languages=all"
CONFIG+=" --enable-ld=yes"
CONFIG+=" --enable-gold=yes"
CONFIG+=" --enable-libstdcxx-debug"
CONFIG+=" --enable-libstdcxx-time=yes"
CONFIG+=" --enable-linker-build-id" 
CONFIG+=" --enable-lto"
CONFIG+=" --enable-plugins"
CONFIG+=" --enable-threads=posix"
CONFIG+=" --host=x86_64-linux-gnu"
CONFIG+=" --target=x86_64-linux-gnu"
CONFIG+=" --with-pkgversion=GCC-Explorer"
CONFIG+=" --with-system-zlib"
CONFIG+=" --disable-werror"  # for 4.9 in-tree bintuils
CONFIG+=" ${DEP_CONFIG}"

# Setting LDFLAGS to add an RPATH in configure is broken, sadly. We also
# need to work around some other Makefile bugs by exporting an LD_LIBRARY_PATH.
export LD_LIBRARY_PATH
export LIBRARY_PATH=/usr/lib/x86_64-linux-gnu

mkdir -p objdir
pushd objdir
../gcc-${VERSION}/configure --prefix ${STAGING_DIR} ${CONFIG}
make -j4
make install
popd

for deplib in ${BUILD_DIR}/*; do
    cp -a $deplib/* ${STAGING_DIR}/
done

# Fix up rpath
EXECUTABLES=$(find ${STAGING_DIR} -type f -perm /u+x | xargs file | grep -E 'ELF.*executable' | cut -f1 -d:)
for executable in ${EXECUTABLES}; do
    root=${executable##${STAGING_DIR}}
    base=\$ORIGIN/$(dirname $root | sed -r -e 's|\./||g' -e 's|[^/]+|..|g')
    ${ROOT}/patchelf --set-rpath ${base}/lib:${base}/lib64 ${executable}
done

# Work around insane in-tree built ld issue
for bindir in ${STAGING_DIR}/{,x86_64-linux-gnu/}bin
do
    pushd ${bindir}
    ln -s ld ld-new
    popd
done

tar zcf gcc.tar.gz -C ${STAGING_DIR} .
