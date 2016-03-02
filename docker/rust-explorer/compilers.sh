#/bin/bash

set -e

cd /opt
curl http://nixos.org/releases/patchelf/patchelf-0.8/patchelf-0.8.tar.gz | tar zxf -
cd patchelf-0.8
./configure
make

do_install() {
    local DIR=$1
    local INSTALL=$2
    cd /opt
    curl -v -L http://static.rust-lang.org/dist/${DIR}.tar.gz | tar zxf -
    cd ${DIR}
    ./install.sh --prefix=/opt/${INSTALL}
    cd /opt
    rm -rf ${DIR}
}

install_rust() {
    local NAME=$1

    do_install rustc-${NAME}-x86_64-unknown-linux-gnu rust-${NAME}
    
    # workaround for LD_LIBRARY_PATH
    for to_patch in /opt/rust-${NAME}/bin/rustc $(find /opt/rust-${NAME}/lib -name *.so); do
    	/opt/patchelf-0.8/src/patchelf --set-rpath /opt/rust-${NAME}/lib $to_patch
    done
    
    # Don't need docs
    rm -rf /opt/rust-${NAME}/share
}

install_new_rust() {
    local NAME=$1

    do_install rustc-${NAME}-x86_64-unknown-linux-gnu rust-${NAME}
    do_install rust-std-${NAME}-x86_64-unknown-linux-gnu rust-${NAME}
    
    # workaround for LD_LIBRARY_PATH
    for to_patch in /opt/rust-${NAME}/bin/rustc $(find /opt/rust-${NAME}/lib -name *.so); do
    	/opt/patchelf-0.8/src/patchelf --set-rpath /opt/rust-${NAME}/lib $to_patch
    done
    
    # Don't need docs
    rm -rf /opt/rust-${NAME}/share
}


install_new_rust nightly
install_new_rust beta
install_new_rust 1.5.0
install_new_rust 1.6.0
install_new_rust 1.7.0

install_rust 1.0.0
install_rust 1.1.0
install_rust 1.2.0
install_rust 1.3.0
install_rust 1.4.0

find /opt -executable -type f | xargs strip || true
rm -rf /opt/patchelf-0.8
