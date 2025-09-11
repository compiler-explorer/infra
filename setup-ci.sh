#!/bin/bash

set -exuo pipefail

# NB this is run from the steps in (private) https://github.com/compiler-explorer/ce-ci

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${DIR}"

env EXTRA_NFS_ARGS="" "${DIR}/setup-common.sh" ci

# In order to run older compilers like gcc 1.27, we need to support running 32-bit code
dpkg --add-architecture i386
add-apt-repository -y ppa:ubuntu-toolchain-r/test

apt-get -y install \
    software-properties-common \
    git \
    gcc-11 \
    g++-11 \
    file \
    build-essential \
    binutils-multiarch \
    bison \
    texinfo \
    flex \
    gawk \
    pkg-config \
    bzip2 \
    unzip \
    curl \
    wget \
    openssh-client \
    autoconf \
    make \
    cmake \
    ninja-build \
    elfutils \
    python-is-python3 \
    python3-pip \
    python3-venv \
    xz-utils \
    libc6-dev:i386 \
    libc6-dev-i386 \
    linux-libc-dev \
    libelf-dev \
    libgmp3-dev \
    libunwind-dev \
    libzstd-dev \
    libdw-dev \
    libboost-all-dev \
    zlib1g-dev

ln -s /efs/squash-images /opt/squash-images
ln -s /efs/compiler-explorer /opt/compiler-explorer
ln -s /efs/wine-stable /opt/wine-stable
