#!/bin/bash

set -ex

[[ -f /site.sh ]] && . /site.sh

[[ ! -e /gcc-explorer/.git ]] && git clone https://github.com/mattgodbolt/gcc-explorer.git /gcc-explorer
cd /gcc-explorer
git checkout ${BRANCH-release}
git pull
PATH=/opt/gcc-explorer/gdc5.2.0/x86_64-pc-linux-gnu/bin:$PATH make dist
