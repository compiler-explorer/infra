#!/bin/bash

# This script installs all the compilers from s3 into a dir in /opt.
# On EC2 this location is on an EFS drive.

OPT=/opt/gcc-explorer

set -ex
mkdir -p ${OPT}
cd ${OPT}

PATCHELF=${OPT}/patchelf-0.8/src/patchelf
if [[ ! -f $PATCHELF ]]; then
    curl http://nixos.org/releases/patchelf/patchelf-0.8/patchelf-0.8.tar.gz | tar zxf -
    cd patchelf-0.8
    ./configure
    make -j$(nproc)
fi

do_strip() {
    find $1 -executable -type f | xargs strip || true
    find $1 -executable -type f | xargs --max-procs=$(nproc) -n 1 -I '{}' bash -c 'upx {} || true'
}

do_rust_install() {
    local DIR=$1
    local INSTALL=$2
    cd ${OPT}
    curl -v -L http://static.rust-lang.org/dist/${DIR}.tar.gz | tar zxf -
    cd ${DIR}
    ./install.sh --prefix=${OPT}/${INSTALL}
    cd ${OPT}
    rm -rf ${DIR}
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
    for to_patch in ${OPT}/rust-${NAME}/bin/rustc $(find ${OPT}/rust-${NAME}/lib -name *.so); do
        ${PATCHELF} --set-rpath ${OPT}/rust-${NAME}/lib $to_patch
    done
    
    # Don't need docs
    rm -rf ${OPT}/rust-${NAME}/share

    do_strip ${OPT}/rust-${NAME}
}

install_new_rust() {
    local NAME=$1

	if [[ -d rust-${NAME} ]]; then
        echo Skipping install of rust $NAME as already installed
		return
	fi
    echo Installing rust $NAME

    do_rust_install rustc-${NAME}-x86_64-unknown-linux-gnu rust-${NAME}
    do_rust_install rust-std-${NAME}-x86_64-unknown-linux-gnu rust-${NAME}
    
    # workaround for LD_LIBRARY_PATH
    for to_patch in ${OPT}/rust-${NAME}/bin/rustc $(find ${OPT}/rust-${NAME}/lib -name *.so); do
        ${PATCHELF} --set-rpath ${OPT}/rust-${NAME}/lib $to_patch
    done
    
    # Don't need docs
    rm -rf ${OPT}/rust-${NAME}/share

    do_strip ${OPT}/rust-${NAME}
}

#########################
# RUST

install_new_rust nightly
install_new_rust beta
install_new_rust 1.5.0
install_new_rust 1.6.0
install_new_rust 1.7.0
install_new_rust 1.8.0
install_new_rust 1.9.0
install_new_rust 1.10.0
install_new_rust 1.11.0

install_rust 1.0.0
install_rust 1.1.0
install_rust 1.2.0
install_rust 1.3.0
install_rust 1.4.0
#########################

#########################
# GO
if [[ ! -d ${OPT}/go ]]; then
    curl https://storage.googleapis.com/golang/go1.4.1.linux-amd64.tar.gz | tar zxf -
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
    curl -L ftp://ftp.gdcproject.org/binaries/${vers}/x86_64-linux-gnu/gdc-${vers}+${build}.tar.xz | tar Jxf -
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
    curl -L https://github.com/ldc-developers/ldc/releases/download/v$vers/ldc2-${vers}-linux-x86_64.tar.xz | tar Jxf -    
    do_strip ldc2-${vers}-linux-x86_64/bin
    popd
}

getgdc 4.8.2 2.064.2
getgdc 4.9.3 2.066.1
getgdc 5.2.0 2.066.1
getldc 0.17.2
getldc 1.0.0
#########################

#########################
# C++
# 12.04 compilers (mostly)
for compiler in clang-3.2.tar.gz \
    clang-3.3.tar.gz \
    intel.tar.gz
do
    DIR=${compiler%.tar.*}
	if [[ ! -d ${DIR} ]]; then
		s3cmd get --force s3://gcc-explorer/opt/$compiler ${OPT}/$compiler
		tar zxf $compiler
		rm $compiler
		do_strip ${DIR}
	fi
done
# Workaround for Intel license
mkdir -p ${OPT}/composer_xe_2013.1.117/Licenses/
cp ${OPT}/intel/licenses/* ${OPT}/composer_xe_2013.1.117/Licenses/

# clangs
for clang in 3.4.1-x86_64-unknown-ubuntu12.04 \
    3.5.1-x86_64-linux-gnu \
    3.5.2-x86_64-linux-gnu-ubuntu-14.04 \
    3.6.2-x86_64-linux-gnu-ubuntu-14.04 \
    3.7.0-x86_64-linux-gnu-ubuntu-14.04 \
    3.7.1-x86_64-linux-gnu-ubuntu-14.04 \
    3.8.0-x86_64-linux-gnu-ubuntu-14.04 \
    3.8.1-x86_64-linux-gnu-ubuntu-14.04 \
    3.9.0-x86_64-linux-gnu-ubuntu-16.04 \
;do
    DIR=clang+llvm-${clang}
    VERSION=$(echo ${clang} | grep -oE '^[0-9.]+')
    if [[ "${VERSION}" = "3.5.2" ]]; then
        # stupid naming issue on clang
        DIR=clang+llvm-3.5.2-x86_64-linux-gnu
    fi
    if [[ ! -d ${DIR} ]]; then
        curl http://llvm.org/releases/${VERSION}/clang+llvm-${clang}.tar.xz | tar Jxf -
        do_strip ${DIR}
    fi
done

# Custom-built GCCs are already UPX's and stripped
# (notes on various compiler builds below:
# 4.7.0 fails to build with a libgcc compile error:
#   ./md-unwind-support.h:144:17: error: field 'info' has incomplete type
# )
for version in \
    4.7.{1,2,3,4} \
    4.8.{1,2,3,4,5} \
    4.9.{0,1,2,3,4} \
    5.{1,2,3,4}.0 \
    6.{1,2}.0 \
; do
    if [[ ! -d gcc-${version} ]]; then
        compiler=gcc-${version}.tar.xz
        s3cmd get --force s3://gcc-explorer/opt/$compiler ${OPT}/$compiler
        tar axf $compiler
        rm $compiler
    fi
done

# snapshots
for major in 7; do
    compilers=$(s3cmd ls s3://gcc-explorer/opt/ | grep -oE "gcc-${major}-[0-9]+" | sort)
    compiler_array=(${compilers})
    latest=${compiler_array[-1]}
    # Extract the latest...
    if [[ ! -d ${latest} ]]; then
        s3cmd get --force s3://gcc-explorer/opt/${latest}.tar.xz ${OPT}/$latest.tar.xz
        tar axf $latest.tar.xz
        rm $latest.tar.xz
    fi
    # Ensure the symlink points at the latest
    rm -f ${OPT}/gcc-${major}-snapshot
    ln -s ${latest} ${OPT}/gcc-${major}-snapshot
    # Clean up any old snapshots
    for compiler in ${compiler-array}; do
        if [[ -d ${compiler} ]]; then
            if [[ "${compiler}" != "${latest}" ]]; then
                rm -rf ${compiler}
            fi
        fi
    done
done

# ICCs also UPX'd
for version in 2016.3.210; do
    if [[ ! -d intel-${version} ]]; then
        compiler=intel-${version}.tar.xz
        s3cmd get --force s3://gcc-explorer/opt/$compiler ${OPT}/$compiler
        tar axf $compiler
        rm $compiler
    fi
done

# Oracle dev studio is stored on s3 only as it's behind a login screen on the
# oracle site. It doesn't like being strip()ped
for version in 12.5; do
    fullname=OracleDeveloperStudio${version}-linux-x86-bin
    if [[ ! -d ${fullname} ]]; then
        compiler=${fullname}.tar.bz2
        s3cmd get --force s3://gcc-explorer/opt/$compiler ${OPT}/$compiler
        tar axf $compiler
        rm $compiler
    fi
done

#########################
