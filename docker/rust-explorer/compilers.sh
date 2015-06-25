#/bin/bash

set -e

cd /opt
curl http://nixos.org/releases/patchelf/patchelf-0.8/patchelf-0.8.tar.gz | tar zxf -
cd patchelf-0.8
./configure
make

install_rust() {
    local NAME=$1

    cd /opt
    curl http://static.rust-lang.org/dist/rust-${NAME}-x86_64-unknown-linux-gnu.tar.gz | tar zxf -
    cd rust-${NAME}-x86_64-unknown-linux-gnu
    ./install.sh --prefix=/opt/rust-${NAME}
    cd /opt
    rm -rf rust-${NAME}-x86_64-unknown-linux-gnu
    
    # workaround for LD_LIBRARY_PATH
    for to_patch in /opt/rust-${NAME}/bin/rustc $(find /opt/rust-${NAME}/lib -name *.so); do
    	/opt/patchelf-0.8/src/patchelf --set-rpath /opt/rust-${NAME}/lib $to_patch
    done
    
    # Don't need docs
    rm -rf /opt/rust-${NAME}/share
}

install_rust nightly
install_rust 1.0.0
find /opt -executable -type f | xargs strip || true
rm -rf /opt/patchelf-0.8
