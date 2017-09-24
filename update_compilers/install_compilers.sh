#!/bin/bash

# This script installs all the free compilers from s3 into a dir in /opt.
# On EC2 this location is on an EFS drive.

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
. ${DIR}/common.inc

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
ALL_COMPILERS=$(python ${DIR}/list_compilers.py --s3url ${S3BUCKET} --prefix ${SUBDIR}/)

PATCHELF=${OPT}/patchelf-0.8/src/patchelf
if [[ ! -f $PATCHELF ]]; then
    if [[ -f /sbin/apk ]]; then
        # Assume we're under alpine
        apk --update add alpine-sdk
    fi
    fetch http://nixos.org/releases/patchelf/patchelf-0.8/patchelf-0.8.tar.gz | tar zxf -
    pushd patchelf-0.8
    CFLAGS=-static LDFLAGS=-static CXXFLAGS=-static ./configure
    make -j$(nproc)
    popd
fi

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

#########################
# RUST
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

install_rust 1.0.0
install_rust 1.1.0
install_rust 1.2.0
install_rust 1.3.0
install_rust 1.4.0
#########################

#########################
# GO
if [[ ! -d ${OPT}/go ]]; then
    fetch https://storage.googleapis.com/golang/go1.4.1.linux-amd64.tar.gz | tar zxf -
    do_strip ${OPT}/go
fi
#########################


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
    vers=$(curl ${https_proxy:+--proxy $https_proxy} https://ldc-developers.github.io/LATEST_BETA)
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

getgdc 4.8.2 2.064.2
getgdc 4.9.3 2.066.1
getgdc 5.2.0 2.066.1
getldc 0.17.2
getldc 1.0.0
getldc 1.1.0
getldc 1.2.0
getldc 1.3.0
getldc 1.4.0
getldc_latestbeta
getldc_s3 1.2.0

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
        fetch http://ellcc.org/releases/ellcc-x86_64-linux-${VERSION}.tgz  | tar xzf -
        mv ellcc ${DIR}
        do_strip ${DIR}
    fi
done


# Custom-built GCCs are already UPX's and stripped
# (notes on various compiler builds below:
# 4.7.0 fails to build with a libgcc compile error:
#   ./md-unwind-support.h:144:17: error: field 'info' has incomplete type
#   (which could now be fixed with the unwind patch if I cared to do so)
# )
for version in \
    4.4.7 \
    4.5.3 \
    4.6.4 \
    4.7.{1,2,3,4} \
    4.8.{1,2,3,4,5} \
    4.9.{0,1,2,3,4} \
    5.{1,2,3,4}.0 \
    6.{1,2,3}.0 \
    7.1.0 \
    7.2.0 \
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
#gcc_arch_install arm 7.1.0
gcc_arch_install arm64 5.4.0
gcc_arch_install arm64 6.3.0
#gcc_arch_install arm64 7.1.0
gcc_arch_install mips 5.4.0
gcc_arch_install mips64 5.4.0
gcc_arch_install mipsel 5.4.0
gcc_arch_install mips64el 5.4.0

if install_nightly; then
    # snapshots/trunk
    compilers=$(echo $ALL_COMPILERS | grep -oE 'gcc-(7|trunk)-[0-9]+' | sort)
    compiler_array=(${compilers})
    latest=${compiler_array[-1]}
    # Extract the latest...
    if [[ ! -d ${latest} ]]; then
        fetch ${S3URL}/${latest}.tar.xz | tar Jxf -
    fi
    # Ensure the symlink points at the latest
    rm -f ${OPT}/gcc-snapshot
    ln -s ${latest} ${OPT}/gcc-snapshot
    # Clean up any old snapshots
    for compiler in gcc-{7,trunk}-[0-9]*; do
        if [[ -d ${compiler} ]]; then
            if [[ "${compiler}" != "${latest}" ]]; then
                rm -rf ${compiler}
            fi
        fi
    done
fi

# Custom-built clangs also stripped and UPX'd
for version in \
    3.9.1 \
    4.0.0 \
    4.0.1 \
    5.0.0 \
; do
    if [[ ! -d clang-${version} ]]; then
        compiler=clang-${version}.tar.xz
        fetch ${S3URL}/$compiler ${OPT}/$compiler
        tar axf $compiler
        rm $compiler
    fi
done

if install_nightly; then
    # trunk builds
    compilers=$(echo $ALL_COMPILERS | grep -oE "clang-trunk-[0-9]+" | sort)
    compiler_array=(${compilers})
    latest=${compiler_array[-1]}
    # Extract the latest...
    if [[ ! -d ${latest} ]]; then
        fetch ${S3URL}/${latest}.tar.xz | tar Jxf -
    fi
    # Ensure the symlink points at the latest
    rm -f ${OPT}/clang-trunk
    ln -s ${latest} ${OPT}/clang-trunk
    # Clean up any old snapshots
    for compiler in clang-trunk-[0-9]*; do
        if [[ -d ${compiler} ]]; then
            if [[ "${compiler}" != "${latest}" ]]; then
                rm -rf ${compiler}
            fi
        fi
    done
fi

# Oracle dev studio is stored on s3 only as it's behind a login screen on the
# oracle site. It doesn't like being strip()ped
for version in 12.5; do
    fullname=OracleDeveloperStudio${version}-linux-x86-bin
    if [[ ! -d ${fullname} ]]; then
        compiler=${fullname}.tar.bz2
        fetch ${S3URL}/$compiler | tar Jxf -
    fi
done

# MSP compilers
if [[ ! -d msp430-gcc-5.3.0.219_linux32 ]]; then
    fetch http://software-dl.ti.com/msp430/msp430_public_sw/mcu/msp430/MSPGCC/4_01_00_00/exports/msp430-gcc-4.1.0.0_linux32.tar.bz2 | tar jxf -
    do_strip msp430-gcc-5.3.0.219_linux32
fi
if [[ ! -d msp430-gcc-6.2.1.16_linux64 ]]; then
    fetch http://software-dl.ti.com/msp430/msp430_public_sw/mcu/msp430/MSPGCC/latest/exports/msp430-gcc-6.2.1.16_linux64.tar.bz2 | tar jxf -
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

get_ispc 1.9.1

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

get_swift() {
    local VER=$1
    local DIR=swift-${VER}

    if [[ ! -d ${DIR} ]]; then
        mkdir ${DIR}
        pushd ${DIR}
        fetch https://swift.org/builds/swift-${VER}-release/ubuntu1604/swift-${VER}-RELEASE/swift-${VER}-RELEASE-ubuntu16.04.tar.gz | tar zxf - --strip-components 1
        # work around insane installation issue
        chmod og+r ${DIR}/usr/lib/swift/CoreFoundation/*
        popd
    fi
}

get_swift 3.1.1

#########################

#########################
# node.js

TARGET_NODE_VERSION=v6.11.3
CURRENT_NODE_VERSION=""
if [[ -d node ]]; then
    CURRENT_NODE_VERSION=$(node/bin/node --version)
fi

if [[ "$TARGET_NODE_VERSION" != "$CURRENT_NODE_VERSION" ]]; then
    echo "Installing node $CURRENT_NODE_VERSION"
    rm -rf node
    fetch "https://nodejs.org/dist/${TARGET_NODE_VERSION}/node-${TARGET_NODE_VERSION}-linux-x64.tar.gz" | tar zxf - && mv node-${TARGET_NODE_VERSION}-linux-x64 node
fi
