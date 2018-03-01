FROM ubuntu:16.04
MAINTAINER Matt Godbolt <matt@godbolt.org>

RUN apt update -y && apt upgrade -y && apt upgrade -y && apt install -y \
    bison \
    bzip2 \
    curl \
    file \
    flex \
    gawk \
    g++ \
    gcc \
    libc6-dev-i386 \
    libelf-dev \
    linux-libc-dev \
    make \
    patch \
    s3cmd \
    subversion \
    texinfo \
    upx-ucl \
    wget \
    xz-utils

# We build from a directory that must be at least searchable with
# EPERM on the CE nodes. Older GCCs erroneously search the $prefix
# used during building, and if they hit a path that gives EPERM they
# bail out. /opt/compiler-explorer/* is a safe spot to build these.
RUN mkdir -p /opt/compiler-explorer/gcc-build
COPY build /opt/compiler-explorer/gcc-build

WORKDIR /opt/compiler-explorer/gcc-build
