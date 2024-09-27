#!/bin/bash

set -exuo pipefail

# NB this is run from the steps in (private) https://github.com/compiler-explorer/ce-ci

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${DIR}"

env EXTRA_NFS_ARGS="" "${DIR}/setup-common.sh" ci

apt-get -y install \
    software-properties-common \
    git \
    gcc \
    g++ \
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
    python3-pip \
    python3.9-venv \
    python3.9 \
    xz-utils \
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
