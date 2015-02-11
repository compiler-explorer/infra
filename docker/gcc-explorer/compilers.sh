#/bin/bash

set -e
cd /opt

curl http://llvm.org/releases/3.5.1/clang+llvm-3.5.1-x86_64-linux-gnu.tar.xz | tar Jxf -

find /opt -executable -type f | xargs strip || true
