#!/bin/bash

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
. ${SCRIPT_DIR}/common.inc


do_rust_install() {
    local DIR=$1
    local INSTALL=$2
    local IS_STD_LIB=1
    if [[ ${DIR} = rust-std-* ]]; then
        IS_STD_LIB=0
    fi
    fetch http://static.rust-lang.org/dist/${DIR}.tar.gz | tar zxvf - -C /tmp || return ${IS_STD_LIB}
    pushd /tmp/${DIR}
    if [[ ${IS_STD_LIB} -ne 0 ]]; then
        rm -rf ${OPT}/${INSTALL}
    fi
    # TODO: remove once rust fixes nightly builds upstream
    # workaround line ending issue in certain rust nightly archives
    dos2unix install.sh
    ./install.sh --prefix=${OPT}/${INSTALL} --verbose --without=rust-docs
    popd
    rm -rf /tmp/${DIR}
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
    local -a TARGETS=("${!2}")
    local FORCE=$3
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
    elif [[ -d rust-${NAME} ]]; then
        echo Skipping install of rust $NAME as already installed
        return
    fi
    echo Installing rust $NAME

    do_rust_install rust-${NAME}-x86_64-unknown-linux-gnu rust-${NAME}
    for TARGET in "${TARGETS[@]}"; do
        do_rust_install rust-std-${NAME}-${TARGET} rust-${NAME}
    done

    # workaround for LD_LIBRARY_PATH
    ${PATCHELF} --set-rpath '$ORIGIN/../lib' ${OPT}/rust-${NAME}/bin/rustc
    ${PATCHELF} --set-rpath '$ORIGIN/../lib' ${OPT}/rust-${NAME}/bin/cargo
    for to_patch in ${OPT}/rust-${NAME}/lib/*.so; do
        ${PATCHELF} --set-rpath '$ORIGIN' $to_patch
    done

    # Don't need docs
    rm -rf ${OPT}/rust-${NAME}/share

    # Don't strip (llvm SOs don't seem to like it and segfault during startup)
}

RUST_TARGETS=(
    aarch64-unknown-linux-gnu
    arm-linux-androideabi
    arm-unknown-linux-gnueabi
    arm-unknown-linux-gnueabihf
    i686-apple-darwin
    i686-pc-windows-gnu
    i686-pc-windows-msvc
    i686-unknown-linux-gnu
    mips-unknown-linux-gnu
    mipsel-unknown-linux-gnu
    x86_64-apple-darwin
    x86_64-pc-windows-gnu
    x86_64-pc-windows-msvc
    x86_64-unknown-linux-gnu
    x86_64-unknown-linux-musl
)
install_new_rust 1.5.0 RUST_TARGETS[@]
install_new_rust 1.6.0 RUST_TARGETS[@]
install_new_rust 1.7.0 RUST_TARGETS[@]
RUST_TARGETS+=(
    aarch64-apple-ios
    armv7-apple-ios
    armv7-unknown-linux-gnueabihf
    armv7s-apple-ios
    i386-apple-ios
    powerpc-unknown-linux-gnu
    powerpc64-unknown-linux-gnu
    powerpc64le-unknown-linux-gnu
    x86_64-apple-ios
    x86_64-rumprun-netbsd
)
install_new_rust 1.8.0 RUST_TARGETS[@]
RUST_TARGETS+=(
    i586-pc-windows-msvc
    i686-linux-android
    i686-unknown-freebsd
    mips-unknown-linux-musl
    mipsel-unknown-linux-musl
    x86_64-unknown-freebsd
    x86_64-unknown-netbsd
)
install_new_rust 1.9.0 RUST_TARGETS[@]
RUST_TARGETS+=(
    aarch64-linux-android
    armv7-linux-androideabi
    i586-unknown-linux-gnu
    i686-unknown-linux-musl
)
install_new_rust 1.10.0 RUST_TARGETS[@]
install_new_rust 1.11.0 RUST_TARGETS[@]
install_new_rust 1.12.0 RUST_TARGETS[@]
RUST_TARGETS+=(
    mips64-unknown-linux-gnuabi64
    mips64el-unknown-linux-gnuabi64
    s390x-unknown-linux-gnu
)
install_new_rust 1.13.0 RUST_TARGETS[@]
RUST_TARGETS+=(
    arm-unknown-linux-musleabi
    arm-unknown-linux-musleabihf
    armv7-unknown-linux-musleabihf
    asmjs-unknown-emscripten
    wasm32-unknown-emscripten
)
install_new_rust 1.14.0 RUST_TARGETS[@]
install_new_rust 1.15.1 RUST_TARGETS[@]
install_new_rust 1.16.0 RUST_TARGETS[@]
RUST_TARGETS+=(
    aarch64-unknown-fuchsia
    sparc64-unknown-linux-gnu
    x86_64-unknown-fuchsia
)
install_new_rust 1.17.0 RUST_TARGETS[@]
RUST_TARGETS+=(
    x86_64-linux-android
)
install_new_rust 1.18.0 RUST_TARGETS[@]
install_new_rust 1.19.0 RUST_TARGETS[@]
install_new_rust 1.20.0 RUST_TARGETS[@]
RUST_TARGETS+=(
    x86_64-unknown-redox
)
install_new_rust 1.21.0 RUST_TARGETS[@]
RUST_TARGETS+=(
    aarch64-unknown-linux-musl
    sparcv9-sun-solaris
    x86_64-sun-solaris
)
install_new_rust 1.22.0 RUST_TARGETS[@]
RUST_TARGETS+=(
    x86_64-unknown-linux-gnux32
)
install_new_rust 1.23.0 RUST_TARGETS[@]
RUST_TARGETS+=(
    armv5te-unknown-linux-gnueabi
    wasm32-unknown-unknown
)
install_new_rust 1.24.0 RUST_TARGETS[@]
RUST_TARGETS+=(
    i586-unknown-linux-musl
    x86_64-unknown-cloudabi
)
install_new_rust 1.25.0 RUST_TARGETS[@]
install_new_rust 1.26.0 RUST_TARGETS[@]
RUST_TARGETS+=(
    armv5te-unknown-linux-musleabi
    thumbv6m-none-eabi
    thumbv7em-none-eabi
    thumbv7em-none-eabihf
    thumbv7m-none-eabi
)
install_new_rust 1.27.0 RUST_TARGETS[@]
install_new_rust 1.27.1 RUST_TARGETS[@]
install_new_rust 1.28.0 RUST_TARGETS[@]
install_new_rust 1.29.0 RUST_TARGETS[@]
install_new_rust 1.30.0 RUST_TARGETS[@]
install_new_rust 1.31.0 RUST_TARGETS[@]
install_new_rust 1.32.0 RUST_TARGETS[@]
RUST_TARGETS+=(
    thumbv7neon-unknown-linux-gnueabihf
    thumbv7neon-linux-androideabi
)
install_new_rust 1.33.0 RUST_TARGETS[@]
RUST_TARGETS+=(
    riscv32imac-unknown-none-elf
    riscv32imc-unknown-none-elf
    riscv64imac-unknown-none-elf
    riscv64gc-unknown-none-elf
)
install_new_rust 1.34.0 RUST_TARGETS[@]
RUST_TARGETS+=(
    armv6-unknown-freebsd-gnueabihf
    armv7-unknown-freebsd-gnueabihf
    wasm32-unknown-wasi
)
install_new_rust 1.35.0 RUST_TARGETS[@]
install_new_rust 1.36.0 RUST_TARGETS[@]
if install_nightly; then
    install_new_rust nightly RUST_TARGETS[@] '1 day'
    install_new_rust beta RUST_TARGETS[@] '1 week'
fi

install_rust 1.0.0
install_rust 1.1.0
install_rust 1.2.0
install_rust 1.3.0
install_rust 1.4.0

