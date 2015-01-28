#/bin/bash

set -e
cd /opt

for compiler in clang-3.2.tar.gz \
    clang-3.3.tar.gz \
    gcc-4.9.0-0909-concepts.tar.gz \
    gcc-4.9.0-with-concepts.tar.gz \
    gcc-4.9.0.tar.gz \
    intel.tar.gz \
    ; do
    s3cmd --config /root/.s3cfg get s3://gcc-explorer/opt/$compiler /opt/$compiler
    tar zxf $compiler
    rm $compiler
done

curl http://llvm.org/releases/3.4.1/clang+llvm-3.4.1-x86_64-unknown-ubuntu12.04.tar.xz | tar Jxf -
