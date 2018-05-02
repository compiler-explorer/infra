#!/bin/bash

# This script installs all the free compilers from s3 into a dir in /opt.
# On EC2 this location is on an EFS drive.

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
. ${SCRIPT_DIR}/common.inc

ARG1="$1"
install_nightly() {
    if [[ "$ARG1" = "nightly" ]]; then
        return 0
    else
        return 1
    fi
}

if install_nightly; then
    echo "Installing nightly builds"
else
    echo "Skipping install of nightly compilers"
fi

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

#########################
# Rust
do_rust_install() {
    local DIR=$1
    local INSTALL=$2
    pushd /tmp
    fetch http://static.rust-lang.org/dist/${DIR}.tar.gz | tar zxvf -
    cd ${DIR}
    ./install.sh --prefix=${OPT}/${INSTALL} --verbose --without=rust-docs
    rm -rf /tmp/${DIR}
    popd
}

install_rust() {
    local NAME=$1

	if [[ -d rust-${NAME} ]]; then
        echo Skipping install of rust $NAME as already installed
		return
	fi
    echo Installing rust $NAME

    do_rust_install rustc-${NAME}-x86_64-unknown-linux-gnu rust-${NAME}

    # workaround for LD_LIBRARY_PATH
    ${PATCHELF} --set-rpath '$ORIGIN/../lib' ${OPT}/rust-${NAME}/bin/rustc
    for to_patch in ${OPT}/rust-${NAME}/lib/*.so; do
        ${PATCHELF} --set-rpath '$ORIGIN' $to_patch
    done
    
    # Don't need docs
    rm -rf ${OPT}/rust-${NAME}/share
    
    do_strip ${OPT}/rust-${NAME}
}

install_new_rust() {
    local NAME=$1
    local FORCE=$2
    local DIR=rust-${NAME}
    
    if [[ -n "$FORCE" && -d ${DIR} ]]; then
        local time_from=$(date -d "now - $FORCE" +%s)
        local dir_time=$(date -r ${DIR} +%s)
        if (( dir_time > time_from )); then
            echo "Treating ${DIR} as up to date enough, despite force"
            FORCE=""
        fi
    fi

    # force install if asked, or if there's no 'cargo' (which used to happen with older builds)
    if [[ -n "${FORCE}" || ! -x rust-${NAME}/bin/cargo ]]; then
        echo Forcing install of $NAME
        rm -rf rust-${NAME}
    fi

	if [[ -d rust-${NAME} ]]; then
        echo Skipping install of rust $NAME as already installed
		return
	fi
    echo Installing rust $NAME

    do_rust_install rust-${NAME}-x86_64-unknown-linux-gnu rust-${NAME}
    
    # workaround for LD_LIBRARY_PATH
    ${PATCHELF} --set-rpath '$ORIGIN/../lib' ${OPT}/rust-${NAME}/bin/rustc
    ${PATCHELF} --set-rpath '$ORIGIN/../lib' ${OPT}/rust-${NAME}/bin/cargo
    for to_patch in ${OPT}/rust-${NAME}/lib/*.so; do
        ${PATCHELF} --set-rpath '$ORIGIN' $to_patch
    done
    
    # Don't need docs
    rm -rf ${OPT}/rust-${NAME}/share

    do_strip ${OPT}/rust-${NAME}
}


if install_nightly; then
    install_new_rust nightly '1 day'
    install_new_rust beta '1 week'
fi
install_new_rust 1.5.0
install_new_rust 1.6.0
install_new_rust 1.7.0
install_new_rust 1.8.0
install_new_rust 1.9.0
install_new_rust 1.10.0
install_new_rust 1.11.0
install_new_rust 1.12.0
install_new_rust 1.13.0
install_new_rust 1.14.0
install_new_rust 1.15.1
install_new_rust 1.16.0
install_new_rust 1.17.0
install_new_rust 1.18.0
install_new_rust 1.19.0
install_new_rust 1.20.0
install_new_rust 1.21.0
install_new_rust 1.22.0
install_new_rust 1.23.0
install_new_rust 1.24.0
install_new_rust 1.25.0

install_rust 1.0.0
install_rust 1.1.0
install_rust 1.2.0
install_rust 1.3.0
install_rust 1.4.0


#########################
# Go

## Install 1.4.1 the old way...
if [[ ! -d ${OPT}/go ]]; then
    fetch https://storage.googleapis.com/golang/go1.4.1.linux-amd64.tar.gz | tar zxf -
    do_strip ${OPT}/go
fi

install_golang() {
    local VERSION=$1
    local DIR=golang-${VERSION}
    if [[ -d ${DIR} ]]; then
        echo Golang $VERSION already intalled, skipping
        return
    fi
    mkdir ${DIR}
    pushd ${DIR}
    fetch https://storage.googleapis.com/golang/go${VERSION}.linux-amd64.tar.gz | tar zxf -
    popd
    do_strip ${DIR}
}

install_golang 1.7.2
install_golang 1.8.5
install_golang 1.8.7
install_golang 1.9.2
install_golang 1.9.4
install_golang 1.10
install_golang 1.10.1


#########################
# D

getgdc() {
    vers=$1
    build=$2
    if [[ -d gdc${vers} ]]; then
        echo D ${vers} already installed, skipping
        return
    fi
    mkdir gdc${vers}
    pushd gdc${vers}
    fetch ftp://ftp.gdcproject.org/binaries/${vers}/x86_64-linux-gnu/gdc-${vers}+${build}.tar.xz | tar Jxf -
    # stripping the D libraries seems to upset them, so just strip the exes
    do_strip x86_64-pc-linux-gnu/bin
    do_strip x86_64-pc-linux-gnu/libexec
    popd
}

getldc() {
    vers=$1
    if [[ -d ldc${vers} ]]; then
        echo LDC ${vers} already installed, skipping
        return
    fi
    mkdir ldc${vers}
    pushd ldc${vers}
    fetch https://github.com/ldc-developers/ldc/releases/download/v${vers}/ldc2-${vers}-linux-x86_64.tar.xz | tar Jxf -    
    # any kind of stripping upsets ldc
    popd
}

getldc_s3() {
    vers=$1
    if [[ -d ldc2-${vers} ]]; then
        echo LDC ${vers} already installed, skipping
        return
    fi
    fetch https://s3.amazonaws.com/compiler-explorer/opt/ldc2-${vers}.tar.xz | tar Jxf -    
}

getldc_latestbeta() {
    vers=$(fetch https://ldc-developers.github.io/LATEST_BETA)
    if [[ ! -d ldcbeta ]]; then
        mkdir ldcbeta
    fi
    pushd ldcbeta
    if [[ "$(cat .version)" = "${vers}" ]]; then
        echo "LDC beta version ${vers} already installed, skipping"
        popd
        return
    fi
    rm -rf *
    fetch https://github.com/ldc-developers/ldc/releases/download/v${vers}/ldc2-${vers}-linux-x86_64.tar.xz | tar Jxf - --strip-components 1
    echo "${vers}" > .version
    # any kind of stripping upsets ldc
    popd
}

getdmd_2x() {
    VER=$1
    DIR=dmd-${VER}
    if [[ -d ${DIR} ]]; then
        echo DMD ${VER} already installed, skipping
        return
    fi
    mkdir ${DIR}
    pushd ${DIR}
    fetch http://downloads.dlang.org/releases/2.x/${VER}/dmd.${VER}.linux.tar.xz | tar Jxf -
    popd
}

getdmd2_nightly() {
    DIR=dmd2-nightly
    if [[ -d ${DIR} ]]; then
        rm -rf ${DIR}
    fi
    mkdir ${DIR}
    pushd ${DIR}
    fetch https://nightlies.dlang.org/dmd-nightly/dmd.master.linux.tar.xz | tar Jxf -
    popd
}

getgdc 4.8.2 2.064.2
getgdc 4.9.3 2.066.1
getgdc 5.2.0 2.066.1
getldc 0.17.2
getldc 1.0.0
getldc 1.1.0
getldc 1.2.0
getldc 1.3.0
getldc 1.4.0
getldc 1.5.0
getldc 1.6.0
getldc 1.7.0
getldc 1.8.0
getldc_latestbeta
getldc_s3 1.2.0
getdmd_2x 2.078.3
getdmd_2x 2.079.0
getdmd_2x 2.079.1
if install_nightly; then
    getdmd2_nightly
fi


#########################
# C++
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
    8.1.0 \
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
; do
    if [[ ! -d clang-${version} ]]; then
        compiler=clang-${version}.tar.xz
        fetch ${S3URL}/$compiler | tar Jxf -
    fi
done

if install_nightly; then
    do_nightly_install clang-trunk clang-trunk
fi

if install_nightly; then
    do_nightly_install clang-cppx-trunk clang-cppx-trunk
fi

if install_nightly; then
    do_nightly_install clang-concepts-trunk clang-concepts-trunk
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

#########################
# C
get_ppci() {
  local VER=$1
  local DIR=ppci-$VER

  if [[ ! -d ${DIR} ]]; then
    fetch https://pypi.io/packages/source/p/ppci/ppci-$VER.tar.gz | tar xfz -
  fi
}

get_ppci 0.5.5


#########################
# Haskell
get_ghc() {
    local VER=$1
    local DIR=ghc-$VER

    if [[ ! -d ${DIR} ]]; then
        pushd /tmp
        fetch https://downloads.haskell.org/~ghc/${VER}/ghc-${VER}-x86_64-deb8-linux.tar.xz | tar Jxf -
        cd /tmp/ghc-${VER}
        ./configure --prefix=${OPT}/${DIR}
        make install
        popd
    fi
}

get_ghc 8.0.2
# Can't install ghc 8.2.1: https://ghc.haskell.org/trac/ghc/ticket/13945
# get_ghc 8.2.1
get_ghc 8.2.2
get_ghc 8.4.1
get_ghc 8.4.2


#########################
# Swift
get_swift() {
    local VER=$1
    local DIR=swift-${VER}

    if [[ ! -d ${DIR} ]]; then
        mkdir ${DIR}
        pushd ${DIR}
        fetch https://swift.org/builds/swift-${VER}-release/ubuntu1604/swift-${VER}-RELEASE/swift-${VER}-RELEASE-ubuntu16.04.tar.gz | tar zxf - --strip-components 1
        # work around insane installation issue
        chmod og+r ./usr/lib/swift/CoreFoundation/*
        popd
    fi
}

get_swift 3.1.1
get_swift 4.0.2
get_swift 4.0.3
get_swift 4.1


#########################
# Pascal
get_fpc() {
    local VER=$1
    local DIR=fpc-$VER.x86_64-linux

    if [[ ! -d ${OPT}/${DIR} ]]; then
        pushd /tmp
        fetch https://downloads.sourceforge.net/project/freepascal/Linux/${VER}/fpc-${VER}.x86_64-linux.tar | tar xf -
        cd ${DIR}
        rm demo.tar.gz
        rm doc-pdf.tar.gz
        rm install.sh
        cp ${SCRIPT_DIR}/custom/install_fpc.sh .
        . install_fpc.sh $VER ${OPT}/${DIR}
        popd
    fi
}

for version in \
    2.6.0 \
    2.6.2 \
    2.6.4 \
    3.0.2 \
    3.0.4 \
; do
    get_fpc $version
done

if [[ ! -d ${OPT}/fpc ]]; then
    mkdir ${OPT}/fpc
fi
cp ${SCRIPT_DIR}/custom/fpc.cfg ${OPT}/fpc/fpc.cfg

#########################
# Assembly

get_nasm() {
    local VER=$1
    local DIR=nasm-$VER

    if [[ ! -d ${OPT}/${DIR} ]]; then
        pushd /tmp
        fetch http://www.nasm.us/pub/nasm/releasebuilds/${VER}/nasm-${VER}.tar.xz | tar Jxf -
        cd ${DIR}
        sh configure
        make
        mkdir ${OPT}/${DIR}
        cp nasm ${OPT}/${DIR}
        popd
    fi
}

for version in \
    2.12.02 \
    2.13.02 \
    2.13.03 \
; do
    get_nasm $version
done
