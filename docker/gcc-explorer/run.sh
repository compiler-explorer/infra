#!/bin/bash

set -ex

. /site.sh

[[ ! -e /gcc-explorer/.git ]] && git clone -b ${BRANCH} --depth 1 https://github.com/mattgodbolt/gcc-explorer.git /gcc-explorer
cd /gcc-explorer
git pull
rm -rf node_modules
cp -r /tmp/node_modules .
make prereqs
nodejs app.js --env amazon --port 10240 --lang C++
