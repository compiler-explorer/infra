#!/bin/bash

set -ex

export CONAN_PASSWORD=$1
LANGUAGE=$2
LIBRARYTOBUILD=$3
FORCECOMPILER=$4

FORCECOMPILERPARAM=""
if [ "$FORCECOMPILER" = "popular-compilers-only" ]; then
  FORCECOMPILERPARAM="--popular-compilers-only"
elif [ "$FORCECOMPILER" != "all" ]; then
  FORCECOMPILERPARAM="--buildfor=$FORCECOMPILER"
fi

LIBRARYPARAM="libraries/$LANGUAGE"
if [ "$LIBRARYTOBUILD" != "all" ]; then
  LIBRARYPARAM="libraries/$LANGUAGE/$LIBRARYTOBUILD"
fi

PATH="/root/.pyenv/shims:/root/.pyenv/versions/3.10.16/bin:/opt/compiler-explorer/cmake/bin:$PATH"

mkdir -p /tmp/build
cd /tmp/build
git clone https://github.com/compiler-explorer/infra

cd /tmp/build/infra


export CONAN_USER="ce"
CONHOME=$(conan config home)
export CONAN_HOME=$CONHOME

cp /tmp/build/infra/init/settings.yml "${CONAN_HOME}/settings.yml"
make ce > ceinstall.log

conan user ce -p -r=ceserver
bin/ce_install --staging-dir=/tmp/staging --enable=nightly build "$FORCECOMPILERPARAM" "$LIBRARYPARAM"
