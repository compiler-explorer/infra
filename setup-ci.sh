#!/bin/bash

set -exuo pipefail

# NB this is run from the steps in (private) https://github.com/compiler-explorer/ce-ci

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${DIR}"

env EXTRA_NFS_ARGS="" "${DIR}/setup-common.sh" ci

ARCH=$(dpkg --print-architecture)

# In order to run older compilers like gcc 1.27, we need to support running 32-bit code
if [ "$ARCH" == 'amd64' ]; then
    dpkg --add-architecture i386
fi
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
    linux-libc-dev \
    libelf-dev \
    libgmp3-dev \
    libunwind-dev \
    libzstd-dev \
    libdw-dev \
    libboost-all-dev \
    zlib1g-dev

# x86_64-specific packages for 32-bit support
if [ "$ARCH" == 'amd64' ]; then
    apt-get -y install \
        libc6-dev:i386 \
        libc6-dev-i386
fi
