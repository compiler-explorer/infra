#!/bin/bash

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
. ${SCRIPT_DIR}/common.inc "$@"


S3BUCKET=compiler-explorer
SUBDIR=opt
S3URL=https://s3.amazonaws.com/${S3BUCKET}/${SUBDIR}
ALL_COMPILERS=$(python ${SCRIPT_DIR}/list_compilers.py --s3url https://s3.amazonaws.com/${S3BUCKET} --prefix ${SUBDIR}/)

PATCHELF=${OPT}/patchelf-0.8/src/patchelf
if [[ ! -f $PATCHELF ]]; then
    fetch http://nixos.org/releases/patchelf/patchelf-0.8/patchelf-0.8.tar.gz | tar zxf -
    pushd patchelf-0.8
    CFLAGS=-static LDFLAGS=-static CXXFLAGS=-static ./configure
    make -j$(nproc)
    popd
fi

# 12.04 compilers (mostly)
for compiler in clang-3.2.tar.gz \
    clang-3.3.tar.gz
do
    DIR=${compiler%.tar.*}
    if [[ ! -d ${DIR} ]]; then
        fetch ${S3URL}/$compiler | tar zxf -
        do_strip ${DIR}
    fi
done

# clangs
for clang in \
    3.0-x86_64-linux-Ubuntu-11_10 \
    3.1-x86_64-linux-ubuntu_12.04 \
; do
    DIR=clang+llvm-${clang}
    VERSION=$(echo ${clang} | grep -oE '^[0-9.]+')
    if [[ ! -d ${DIR} ]]; then
        fetch http://llvm.org/releases/${VERSION}/clang+llvm-${clang}.tar.gz | tar zxf -
        do_strip ${DIR}
    fi
done
for clang in \
    3.4.1-x86_64-unknown-ubuntu12.04 \
    3.5.0-x86_64-linux-gnu-ubuntu-14.04 \
    3.5.1-x86_64-linux-gnu \
    3.5.1-x86_64-linux-gnu \
    3.5.2-x86_64-linux-gnu-ubuntu-14.04 \
    3.6.2-x86_64-linux-gnu-ubuntu-14.04 \
    3.7.0-x86_64-linux-gnu-ubuntu-14.04 \
    3.7.1-x86_64-linux-gnu-ubuntu-14.04 \
    3.8.0-x86_64-linux-gnu-ubuntu-14.04 \
    3.8.1-x86_64-linux-gnu-ubuntu-14.04 \
    3.9.0-x86_64-linux-gnu-ubuntu-16.04 \
; do
    DIR=clang+llvm-${clang}
    VERSION=$(echo ${clang} | grep -oE '^[0-9.]+')
    # stupid naming issues on clang
    if [[ "${VERSION}" = "3.5.0" ]]; then
        DIR=clang+llvm-3.5.0-x86_64-linux-gnu
    fi
    if [[ "${VERSION}" = "3.5.2" ]]; then
        DIR=clang+llvm-3.5.2-x86_64-linux-gnu
    fi
    if [[ ! -d ${DIR} ]]; then
        fetch http://llvm.org/releases/${VERSION}/clang+llvm-${clang}.tar.xz | tar Jxf -
        do_strip ${DIR}
    fi
done

# ellccs
for VERSION in 0.1.33 \
               0.1.34 \
; do
    DIR=ellcc-${VERSION}
    if [[ -d ${DIR} ]]; then
        echo ${DIR} installed already
    else
        fetch http://ellcc.org/releases/older-releases/ellcc-x86_64-linux-${VERSION}.tgz  | tar xzf -
        mv ellcc ${DIR}
        do_strip ${DIR}
    fi
done

install_ellcc() {
    for VERSION in "$@"; do
        local DIR=ellcc-${VERSION}
        if [[ ! -d ${DIR} ]]; then
            fetch http://ellcc.org/releases/release-${VERSION}/ellcc-x86_64-linux-${VERSION}.bz2 | tar xjf -
            mv ellcc ${DIR}
            do_strip ${DIR}
        fi
    done
}

install_ellcc 2017-07-16

# Custom-built GCCs are already UPX's and stripped
# (notes on various compiler builds below:
# 4.7.0 fails to build with a libgcc compile error:
#   ./md-unwind-support.h:144:17: error: field 'info' has incomplete type
#   (which could now be fixed with the unwind patch if I cared to do so)
# )
for version in \
    4.1.2 \
    4.4.7 \
    4.5.3 \
    4.6.4 \
    4.7.{1,2,3,4} \
    4.8.{1,2,3,4,5} \
    4.9.{0,1,2,3,4} \
    5.{1,2,3,4,5}.0 \
    6.{1,2,3,4}.0 \
    7.{1,2,3}.0 \
    8.{1,2}.0 \
; do
    if [[ ! -d gcc-${version} ]]; then
        compiler=gcc-${version}.tar.xz
        fetch ${S3URL}/$compiler | tar Jxf -
    fi
done

# other architectures
gcc_arch_install() {
    local arch=$1
    local version=$2
    local xz=${arch}-gcc-${version}.tar.xz
    local dir=${arch}/gcc-${version}
    mkdir -p ${arch}
    if [[ ! -d ${dir} ]]; then
        fetch ${S3URL}/${xz} | tar Jxf - -C ${OPT}/${arch}
    fi
}
gcc_arch_install arm 4.5.4
gcc_arch_install arm 4.6.4
gcc_arch_install avr 4.5.4
gcc_arch_install avr 4.6.4
gcc_arch_install msp430 4.5.3
gcc_arch_install powerpc 4.8.5
gcc_arch_install powerpc64le 6.3.0
gcc_arch_install arm 5.4.0
gcc_arch_install arm 6.3.0
gcc_arch_install arm64 5.4.0
gcc_arch_install arm64 6.3.0
gcc_arch_install mips 5.4.0
gcc_arch_install mips64 5.4.0
gcc_arch_install mipsel 5.4.0
gcc_arch_install mips64el 5.4.0

if [[ ! -d arm/gcc-arm-none-eabi-7-2017-q4-major ]]; then
    pushd arm
    fetch https://developer.arm.com/-/media/Files/downloads/gnu-rm/7-2017q4/gcc-arm-none-eabi-7-2017-q4-major-linux.tar.bz2 | tar jxf -
    popd
fi

do_nightly_install() {
    local COMPILER_PATTERN="$1"
    local DESTINATION="$2"
    # work around a cronic issue where the execution output is interpreted as error
    # if it spans multiple lines: assigning output with multiple lines to a variable
    # fools it.
    set +x
    compilers=$(echo $ALL_COMPILERS | grep -oE "${COMPILER_PATTERN}-[0-9]+" | sort)
    set -x
    compiler_array=(${compilers})
    latest=${compiler_array[-1]}
    # Extract the latest...
    if [[ ! -d ${latest} ]]; then
        fetch ${S3URL}/${latest}.tar.xz | tar Jxf -
    fi
    # Ensure the symlink points at the latest
    rm -f ${OPT}/${DESTINATION}
    ln -s ${latest} ${OPT}/${DESTINATION}
    # Clean up any old snapshots
    for compiler in ${COMPILER_PATTERN}-[0-9]*; do
        if [[ -d ${compiler} ]]; then
            if [[ "${compiler}" != "${latest}" ]]; then
                rm -rf ${compiler}
            fi
        fi
    done
}

if install_nightly; then
    do_nightly_install gcc-trunk gcc-snapshot
fi

# Custom-built clangs also stripped and UPX'd
for version in \
    3.9.1 \
    4.0.0 \
    4.0.1 \
    5.0.0 \
    6.0.0 \
    7.0.0 \
; do
    if [[ ! -d clang-${version} ]]; then
        compiler=clang-${version}.tar.xz
        fetch ${S3URL}/$compiler | tar Jxf -
    fi
done

if install_nightly; then
    do_nightly_install clang-trunk clang-trunk
    do_nightly_install clang-cppx-trunk clang-cppx-trunk
    do_nightly_install clang-concepts-trunk clang-concepts-trunk
    do_nightly_install clang-relocatable-trunk clang-relocatable-trunk
    do_nightly_install clang-autonsdmi-trunk clang-autonsdmi-trunk
fi

# Oracle dev studio is stored on s3 only as it's behind a login screen on the
# oracle site. It doesn't like being strip()ped
for version in 12.5; do
    fullname=OracleDeveloperStudio${version}-linux-x86-bin
    if [[ ! -d ${fullname} ]]; then
        compiler=${fullname}.tar.bz2
        fetch ${S3URL}/$compiler | tar jxf -
    fi
done

# MSP compilers. Website is dead. TODO: Find a new source!
if [[ ! -d msp430-gcc-5.3.0.219_linux32 ]]; then
    fetch http://software-dl.ti.com/msp430/msp430_public_sw/mcu/msp430/MSPGCC/4_01_00_00/exports/msp430-gcc-4.1.0.0_linux32.tar.bz2 | tar jxf -
    do_strip msp430-gcc-5.3.0.219_linux32
fi
if [[ ! -d msp430-gcc-6.2.1.16_linux64 ]]; then
    fetch http://software-dl.ti.com/msp430/msp430_public_sw/mcu/msp430/MSPGCC/5_00_00_00/exports/msp430-gcc-6.2.1.16_linux64.tar.bz2 | tar jxf -
    do_strip msp430-gcc-6.2.1.16_linux64
fi

# GNU ARM Embedded toolchain
if [[ ! -d gcc-arm-none-eabi-5_4-2016q3 ]]; then
    fetch https://launchpad.net/gcc-arm-embedded/5.0/5-2016-q3-update/+download/gcc-arm-none-eabi-5_4-2016q3-20160926-linux.tar.bz2 | tar jxf -
    do_strip gcc-arm-none-eabi-5_4-2016q3
fi

# intel ispc
get_ispc() {
    local VER=$1
    local DIR=ispc-$VER

    if [[ ! -d ${DIR} ]]; then
        mkdir $DIR
        pushd $DIR
        fetch https://sourceforge.net/projects/ispcmirror/files/v$VER/ispc-v$VER-linux.tar.gz \
            | tar zxf - ispc-v$VER-linux/ispc --strip-components 1
        popd
        do_strip $DIR
    fi
}

get_ispc 1.9.2
get_ispc 1.9.1
