FROM ubuntu:16.04
MAINTAINER Matt Godbolt <matt@godbolt.org>

RUN apt-get update -y

RUN apt-get install -y \
    bison \
    bzip2 \
    curl \
    file \
    flex \
    g++ \
    gcc \
    libc6-dev-i386 \
    linux-libc-dev \
    make \
    patch \
    s3cmd \
    texinfo \
    upx-ucl \
    wget \
    xz-utils

RUN mkdir -p /root
COPY build /root/

WORKDIR /root
