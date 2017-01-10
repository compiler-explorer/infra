FROM ubuntu:16.04
MAINTAINER Matt Godbolt <matt@godbolt.org>

RUN apt update -y && apt upgrade -y && apt update -y

RUN apt install -y \
    bison \
    bzip2 \
    cmake \
    curl \
    file \
    flex \
    g++ \
    gcc \
    libc6-dev-i386 \
    linux-libc-dev \
    make \
    patch \
    python \
    s3cmd \
    subversion \
    texinfo \
    upx-ucl \
    wget \
    xz-utils \
    zlib1g-dev

RUN mkdir -p /root
COPY build /root/

WORKDIR /root
