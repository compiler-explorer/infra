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

PYENV_ROOT="/root/.pyenv"
PATH="$PYENV_ROOT/bin:$PYENV_ROOT/shims:$PYENV_ROOT/versions/3.10.16/bin:/home/ubuntu/.local/bin:/opt/compiler-explorer/cmake/bin:$PATH"

mount_opt() {
    mount -a

    mkdir -p /opt/compiler-explorer
    mountpoint /opt/compiler-explorer || mount --bind /efs/compiler-explorer /opt/compiler-explorer

    mkdir -p /opt/intel
    mountpoint /opt/intel || mount --bind /efs/intel /opt/intel

    mkdir -p /opt/arm
    mountpoint /opt/arm || mount --bind /efs/arm /opt/arm

    mkdir -p /opt/qnx
    mountpoint /opt/qnx || mount --bind /efs/qnx /opt/qnx

    [ -f /opt/.health ] || touch /opt/.health
    mountpoint /opt/.health || mount --bind /efs/.health /opt/.health
}

mount_opt

mkdir -p /tmp/build
cd /tmp/build
rm -rf infra
git clone https://github.com/compiler-explorer/infra

cd /tmp/build/infra

python -m pip install conan==1.59
conan remote clean && conan remote add ceserver https://conan.compiler-explorer.com/ True

export CONAN_USER="ce"
CONHOME=$(conan config home)
export CONAN_HOME=$CONHOME

cp /tmp/build/infra/init/settings.yml "${CONAN_HOME}/settings.yml"
make ce > ceinstall.log

conan user ce -p -r=ceserver
bin/ce_install --staging-dir=/tmp/staging --enable=nightly build "$FORCECOMPILERPARAM" "$LIBRARYPARAM"
