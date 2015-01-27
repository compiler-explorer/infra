#/bin/bash

set -e

cd /opt
curl http://static.rust-lang.org/dist/rust-nightly-x86_64-unknown-linux-gnu.tar.gz | tar zxf -
cd rust-nightly-x86_64-unknown-linux-gnu
./install.sh --prefix=/opt/rust-nightly
cd /opt
rm -rf rust-nightly-x86_64-unknown-linux-gnu

# workaround for LD_LIBRARY_PATH
cd /opt
curl http://nixos.org/releases/patchelf/patchelf-0.8/patchelf-0.8.tar.gz | tar zxf -
cd patchelf-0.8
./configure
make
for to_patch in /opt/rust-nightly/bin/rustc $(find /opt/rust-nightly/lib -name *.so); do
	src/patchelf --set-rpath /opt/rust-nightly/lib $to_patch
done
cd ..
rm -rf patchelf-0.8

# Don't need docs
rm -rf /opt/rust-nightly/share
