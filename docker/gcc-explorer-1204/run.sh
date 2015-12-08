#!/bin/bash

set -ex

. /site.sh

git clone -b ${BRANCH} --depth 1 https://github.com/mattgodbolt/gcc-explorer.git /gcc-explorer
cd /gcc-explorer
cp -r /tmp/node_modules .
make prereqs
node app.js --env amazon --env amazon1204 --language C++ --port 20480
