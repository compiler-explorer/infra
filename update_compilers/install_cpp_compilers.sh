#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. ${SCRIPT_DIR}/common.inc

# 12.04 compilers (mostly)
for compiler in clang-3.2.tar.gz \
    clang-3.3.tar.gz; do
    DIR=${compiler%.tar.*}
    if [[ ! -d ${DIR} ]]; then
        fetch ${S3URL}/$compiler | tar zxf -
        do_strip ${DIR}
    fi
done

# clangs
for clang in \
    3.0-x86_64-linux-Ubuntu-11_10 \
    3.1-x86_64-linux-ubuntu_12.04; do
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
    3.9.0-x86_64-linux-gnu-ubuntu-16.04; do
    DIR=clang+llvm-${clang}
    VERSION=$(echo ${clang} | grep -oE '^[0-9.]+')
    # stupid naming issues on clang
    if [[ "${VERSION}" == "3.5.0" ]]; then
        DIR=clang+llvm-3.5.0-x86_64-linux-gnu
    fi
    if [[ "${VERSION}" == "3.5.2" ]]; then
        DIR=clang+llvm-3.5.2-x86_64-linux-gnu
    fi
    if [[ ! -d ${DIR} ]]; then
        fetch http://llvm.org/releases/${VERSION}/clang+llvm-${clang}.tar.xz | tar Jxf -
        do_strip ${DIR}
    fi
done

# ellccs
for VERSION in 0.1.33 \
    0.1.34; do
    DIR=ellcc-${VERSION}
    if [[ -d ${DIR} ]]; then
        echo ${DIR} installed already
    else
        fetch http://ellcc.org/releases/older-releases/ellcc-x86_64-linux-${VERSION}.tgz | tar xzf -
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
    7.{1,2,3,4}.0 \
    8.{1,2,3}.0 \
    9.{1,2}.0; do
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
gcc_arch_install powerpc64le at12
gcc_arch_install powerpc64 at12
gcc_arch_install arm 5.4.0
gcc_arch_install arm 6.3.0
gcc_arch_install arm 6.4.0
gcc_arch_install arm 7.3.0
gcc_arch_install arm 8.2.0
gcc_arch_install arm64 5.4.0
gcc_arch_install arm64 6.3.0
gcc_arch_install arm64 6.4.0
gcc_arch_install arm64 7.3.0
gcc_arch_install arm64 8.2.0
gcc_arch_install mips 5.4.0
gcc_arch_install mips64 5.4.0
gcc_arch_install mipsel 5.4.0
gcc_arch_install mips64el 5.4.0
gcc_arch_install riscv64 8.2.0

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
    compilers=$(echo ${ALL_COMPILERS} | grep -oE "${COMPILER_PATTERN}-[0-9]+" | sort)
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
    do_nightly_install gcc-lock3-contracts-trunk gcc-lock3-contracts-trunk
    do_nightly_install gcc-cxx-modules-trunk gcc-cxx-modules-trunk
fi

# Custom-built clangs also stripped and UPX'd
for version in \
    3.9.1 \
    4.0.0 \
    4.0.1 \
    5.0.0 \
    6.0.0 \
    7.0.0 \
    8.0.0; do
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
    do_nightly_install clang-lifetime-trunk clang-lifetime-trunk
    do_nightly_install clang-parmexpr-trunk clang-parmexpr-trunk
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

# FIRST Robotics/ NI Real-Time Specific toolchain
if [[ ! -d arm/frc2019-6.3.0 ]]; then
    fetch https://github.com/wpilibsuite/toolchain-builder/releases/download/v2019-3/FRC-2019-Linux-Toolchain-6.3.0.tar.gz | tar xzf -
    mv frc2019 arm/frc2019-6.3.0
fi

# Raspbian Specific toolchain
if [[ ! -d arm/raspbian9-6.3.0 ]]; then
    fetch https://github.com/wpilibsuite/raspbian-toolchain/releases/download/v1.3.0/Raspbian9-Linux-Toolchain-6.3.0.tar.gz | tar xzf -
    mv raspbian9 arm/raspbian9-6.3.0
fi

# FIRST Robotics/ NI Real-Time Specific toolchain 2020
if [[ ! -d arm/frc2020-7.3.0 ]]; then
    fetch https://github.com/wpilibsuite/roborio-toolchain/releases/download/v2020-1/FRC-2020-Linux-Toolchain-7.3.0.tar.gz | tar xzf -
    mv frc2020 arm/frc2020-7.3.0
fi

# Raspbian Buster Specific toolchain
if [[ ! -d arm/raspbian10-8.3.0 ]]; then
    fetch https://github.com/wpilibsuite/raspbian-toolchain/releases/download/v2.1.0/Raspbian10-Linux-Toolchain-8.3.0.tar.gz | tar xzf -
    mv raspbian10 arm/raspbian10-8.3.0
fi

# Arduino toolset
if [[ ! -d avr/arduino-1.8.9 ]]; then
    fetch http://downloads.arduino.cc/arduino-1.8.9-linux64.tar.xz | tar xJf -
    mv arduino-1.8.9 avr/arduino-1.8.9
fi

# intel ispc
get_ispc() {
    local VER=$1
    local DIR=ispc-$VER

    if [[ ! -d ${DIR} ]]; then
        mkdir $DIR
        pushd $DIR
        fetch https://sourceforge.net/projects/ispcmirror/files/v$VER/ispc-v$VER-linux.tar.gz/download |
            tar zxf - ispc-$VER-Linux --strip-components 1
        popd
        do_strip $DIR
    fi
}
get_ispc_old() {
    local VER=$1
    local DIR=ispc-$VER

    if [[ ! -d ${DIR} ]]; then
        mkdir $DIR
        pushd $DIR
        fetch https://sourceforge.net/projects/ispcmirror/files/v$VER/ispc-v$VER-linux.tar.gz/download |
            tar zxf - ispc-v$VER-linux-ispc --strip-components 1
        popd
        do_strip $DIR
    fi
}

do_ispc_nightly_install() {
    local COMPILER_PATTERN="$1"
    local DESTINATION="$2"

    # just shell out to the new install system
    "${SCRIPT_DIR}/../bin/ce_install" --enable=nightly install "compilers/ispc/nightly ${COMPILER_PATTERN}"

    # new systtem doesn't yet clean up old nightly installs, so we have to do it here still

    # work around a cronic issue where the execution output is interpreted as error
    # if it spans multiple lines: assigning output with multiple lines to a variable
    # fools it.
    set +x
    compilers=$(ls "${OPT}" | grep -oE "${DESTINATION}-[0-9]+" | sort)
    set -x
    compiler_array=(${compilers})
    latest=${compiler_array[-1]}

    # Clean up any old snapshots
    for compiler in ${DESTINATION}-[0-9]*; do
        if [[ -d ${compiler} ]]; then
            if [[ "${compiler}" != "${latest}" ]]; then
                rm -rf ${compiler}
            fi
        fi
    done
}

get_ispc 1.10.0
get_ispc_old 1.9.2
get_ispc_old 1.9.1

if install_nightly; then
    do_ispc_nightly_install trunk ispc-trunk
fi

# djgpp
get_djgpp() {
    local VER=$1
    local DIR=djgpp-$VER

    declare -A TAG=([5.5.0]=v2.9
        [7.2.0]=v2.8
        [6.4.0]=v2.7
        [7.1.0]=v2.6
        [6.3.0]=v2.6
        [5.4.0]=v2.6
        [4.9.4]=v2.6
        [6.2.0]=v2.1)

    if [[ ! -d ${DIR} ]]; then
        mkdir $DIR
        pushd $DIR
        fetch https://github.com/andrewwutw/build-djgpp/releases/download/${TAG[$VER]}/djgpp-linux64-gcc${VER//./}.tar.bz2 |
            tar jxf - --strip-components 1
        popd
        do_strip $DIR
    fi
}

get_djgpp 7.2.0
get_djgpp 6.4.0
get_djgpp 5.5.0
get_djgpp 4.9.4
