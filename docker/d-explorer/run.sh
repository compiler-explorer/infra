#!/bin/bash

set -ex
. /site.sh

export LIBRARY_PATH=/usr/glibc-compat/lib
export LD_LIBRARY_PATH=/usr/glibc-compat/lib

git clone -b ${BRANCH} --depth 1 https://github.com/mattgodbolt/gcc-explorer.git /gcc-explorer
cd /gcc-explorer
cp -r /tmp/node_modules .
PATH=/opt/gcc-explorer/gdc5.2.0/x86_64-pc-linux-gnu/bin:$PATH make dist
node app.js --env amazon --language d --port 10241 --static out/dist
