#!/bin/bash

set -ex

export CONAN_PASSWORD=$1
LANGUAGE=$2
LIBRARYTOBUILD=$3
FORCECOMPILER=$4
BRANCH=${5:-main}

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

PYENV_ROOT="/opt/pyenv"
# The version is pinned, so address its bin directly rather than going through
# pyenv's shims: a shim re-runs `pyenv rehash` after pip, which wants to write
# to $PYENV_ROOT/shims, and the image ships that tree read-only.
PATH="$PYENV_ROOT/versions/3.10.16/bin:$PYENV_ROOT/bin:/home/ubuntu/.local/bin:/opt/compiler-explorer/cmake/bin:$PATH"

# conan 1.59 pins PyYAML<=6.0, which has no wheel for the 3.12 that Ubuntu
# 24.04 ships, so the build must run on pyenv's 3.10. Fail loudly rather than
# falling through to the system python, which is how this broke silently
# before: pyenv lived under /root and was unreadable to the ubuntu user.
if ! command -v python >/dev/null || [[ "$(command -v python)" != "$PYENV_ROOT"/* ]]; then
  echo "Expected python from $PYENV_ROOT, got '$(command -v python || echo none)'" >&2
  exit 1
fi

git config --global --add safe.directory '*'

mkdir -p /tmp/build
cd /tmp/build
rm -rf infra
git clone --branch "$BRANCH" --single-branch https://github.com/compiler-explorer/infra

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
