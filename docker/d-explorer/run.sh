#!/bin/bash

set -ex

git clone -b release --depth 1 https://github.com/mattgodbolt/gcc-explorer.git /gcc-explorer
cd /gcc-explorer
make prereqs GDC=/usr/bin/gdc-4.9
nodejs app.js --env amazon-d
