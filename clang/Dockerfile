FROM ubuntu:18.04
MAINTAINER Matt Godbolt <matt@godbolt.org>

ARG DEBIAN_FRONTEND=noninteractive
RUN apt update -y -q && apt upgrade -y -q && apt update -y -q && \
    apt install -y -q \
    bison \
    bzip2 \
    cmake \
    curl \
    file \
    flex \
    g++ \
    gcc \
    git \
    libc6-dev-i386 \
    linux-libc-dev \
    make \
    patch \
    python \
    s3cmd \
    subversion \
    texinfo \
    wget \
    xz-utils \
    zlib1g-dev

RUN mkdir -p /root
COPY build /root/

WORKDIR /root
