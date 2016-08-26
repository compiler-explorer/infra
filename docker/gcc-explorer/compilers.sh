#/bin/bash

set -e
cd /opt

curl http://llvm.org/releases/3.5.1/clang+llvm-3.5.1-x86_64-linux-gnu.tar.xz | tar Jxf -
curl http://llvm.org/releases/3.5.2/clang+llvm-3.5.2-x86_64-linux-gnu-ubuntu-14.04.tar.xz | tar Jxf -
curl http://llvm.org/releases/3.6.2/clang+llvm-3.6.2-x86_64-linux-gnu-ubuntu-14.04.tar.xz | tar Jxf -
curl http://llvm.org/releases/3.7.0/clang+llvm-3.7.0-x86_64-linux-gnu-ubuntu-14.04.tar.xz | tar Jxf -
curl http://llvm.org/releases/3.7.1/clang+llvm-3.7.1-x86_64-linux-gnu-ubuntu-14.04.tar.xz | tar Jxf -
curl http://llvm.org/releases/3.8.0/clang+llvm-3.8.0-x86_64-linux-gnu-ubuntu-14.04.tar.xz | tar Jxf -

find /opt -executable -type f | xargs strip || true

# Custom-built GCCs are already UPX's and stripped
for version in 5.1.0 5.2.0 5.3.0 6.1.0 6.2.0; do
    compiler=gcc-${version}.tar.xz
    s3cmd --config /root/.s3cfg get s3://gcc-explorer/opt/$compiler /opt/$compiler
    tar axf $compiler
    rm $compiler
done
