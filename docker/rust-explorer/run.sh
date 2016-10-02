#!/bin/bash

set -ex

. /site.sh

export LIBRARY_PATH=/usr/glibc-compat/lib
export LD_LIBRARY_PATH=/usr/glibc-compat/lib

git clone -b ${BRANCH} --depth 1 https://github.com/mattgodbolt/gcc-explorer.git /gcc-explorer
cd /gcc-explorer
cp -r /tmp/node_modules .
make dist
node app.js --env amazon --language rust --port 10242 --static out/dist
