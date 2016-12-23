#!/bin/bash

set -ex

[[ -f /site.sh ]] && . /site.sh

[[ ! -e /gcc-explorer/.git ]] && git clone https://github.com/mattgodbolt/gcc-explorer.git /gcc-explorer
cd /gcc-explorer
git checkout ${BRANCH-release}
git pull
env PATH=${PATH}:/opt/gcc-explorer/rust-1.14.0/bin make dist
