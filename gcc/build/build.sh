#!/bin/bash

set -e

VERSION=$1
OUTPUT=${2-/root/gcc-${VERSION}.tar.bz2}

# Workaround for Ubuntu builds
export LIBRARY_PATH=/usr/lib/x86_64-linux-gnu
STAGING_DIR=$(pwd)/staging
rm -rf ${STAGING_DIR}
mkdir -p ${STAGING_DIR}

if [[ ! -e gcc-${VERSION}.tar.bz2 ]]; then
    echo "Fetching GCC"
    if echo ${VERSION} | grep 'snapshot-'; then
        VERSION=${VERSION/#snapshot-/}
        curl -L -O ftp://gcc.gnu.org/pub/gcc/snapshots/${VERSION}/gcc-${VERSION}.tar.bz2
    else
        curl -L -O ftp://ftp.gnu.org/gnu/gcc/gcc-${VERSION}/gcc-${VERSION}.tar.bz2
    fi
fi
rm -rf gcc-${VERSION}
echo "Extracting GCC..."
tar jxf gcc-${VERSION}.tar.bz2

BINUTILS_VERSION=2.27
echo "Fetching binutils ${BINUTILS_VERSION}"
if [[ ! -e binutils-${BINUTILS_VERSION}.tar.bz2 ]]; then
    curl -L -O http://ftp.gnu.org/gnu/binutils/binutils-${BINUTILS_VERSION}.tar.bz2
fi
BINUTILS_DIR=binutils-${BINUTILS_VERSION}
rm -rf ${BINUTILS_DIR}
tar jxf binutils-${BINUTILS_VERSION}.tar.bz2
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

echo "Downloading prerequisites"
pushd gcc-${VERSION}
./contrib/download_prerequisites
popd

CONFIG=""
CONFIG+=" --build=x86_64-linux-gnu"
CONFIG+=" --disable-multilibs"
CONFIG+=" --enable-clocale=gnu"
CONFIG+=" --enable-languages=c,c++"
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
CONFIG+=" --with-pkgversion=GCC-Explorer-Build"
CONFIG+=" --with-system-zlib"
CONFIG+=" ${DEP_CONFIG}"

# Setting LDFLAGS to add an RPATH in configure is broken, sadly. We also
# need to work around some other Makefile bugs by exporting an LD_LIBRARY_PATH.
export LD_LIBRARY_PATH
export LIBRARY_PATH=/usr/lib/x86_64-linux-gnu

mkdir -p objdir
pushd objdir
../gcc-${VERSION}/configure --prefix ${STAGING_DIR} ${CONFIG}
make -j$(nproc)
make install-strip
popd

# Fix up rpath
EXECUTABLES=$(find ${STAGING_DIR} -type f -perm /u+x | xargs file | grep -E 'ELF.*executable' | cut -f1 -d:)
for executable in ${EXECUTABLES}; do
    root=${executable##${STAGING_DIR}}
    base=\$ORIGIN/$(dirname $root | sed -r -e 's|\./||g' -e 's|[^/]+|..|g')
    /root/patchelf --set-rpath ${base}/lib:${base}/lib64 ${executable}
done

# Work around insane in-tree built ld issue
for bindir in ${STAGING_DIR}/{,x86_64-linux-gnu/}bin
do
    pushd ${bindir}
    ln -s ld ld-new
    popd
done

upx --best ${STAGING_DIR}/bin/* 
for EXE in cc1 cc1plus collect2 lto1 lto-wrapper; do
    upx --best ${STAGING_DIR}/libexec/gcc/x86_64-linux-gnu/${VERSION}/${EXE}
done

tar jcf ${OUTPUT} -C ${STAGING_DIR} .
