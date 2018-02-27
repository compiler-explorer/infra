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

RUN mkdir -p /root
COPY build /root/

WORKDIR /root
