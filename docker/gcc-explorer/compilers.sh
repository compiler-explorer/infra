#/bin/bash

set -e
cd /opt

curl http://llvm.org/releases/3.5.1/clang+llvm-3.5.1-x86_64-linux-gnu.tar.xz | tar Jxf -
curl http://llvm.org/releases/3.5.2/clang+llvm-3.5.2-x86_64-linux-gnu-ubuntu-14.04.tar.xz | tar Jxf -
curl http://llvm.org/releases/3.6.2/clang+llvm-3.6.2-x86_64-linux-gnu-ubuntu-14.04.tar.xz | tar Jxf -
curl http://llvm.org/releases/3.7.0/clang+llvm-3.7.0-x86_64-linux-gnu-ubuntu-14.04.tar.xz | tar Jxf -

find /opt -executable -type f | xargs strip || true

# gcc 5.x doesn't like being stripped
for compiler in gcc-5.1.0.tar.gz gcc-5.2.0.tar.gz \
    ; do
    s3cmd --config /root/.s3cfg get s3://gcc-explorer/opt/$compiler /opt/$compiler
    tar zxf $compiler
    rm $compiler
done
