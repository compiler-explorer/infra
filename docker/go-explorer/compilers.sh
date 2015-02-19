#/bin/bash

set -e
cd /opt

curl https://storage.googleapis.com/golang/go1.4.1.linux-amd64.tar.gz | tar zxf -

find /opt -executable -type f | xargs strip || true
