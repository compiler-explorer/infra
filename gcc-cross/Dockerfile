FROM ubuntu:16.04
MAINTAINER Matt Godbolt <matt@godbolt.org>

RUN mkdir -p /opt mkdir -p /home/gcc-user && useradd gcc-user && chown gcc-user /opt /home/gcc-user
RUN apt-get update -y && apt-get upgrade -y && apt-get upgrade -y

RUN apt-get install -y \
    autoconf \
    automake \
    libtool \
    bison \
    bzip2 \
    curl \
    file \
    flex \
    gawk \
    gcc \
    g++ \
    gperf \
    help2man \
    libc6-dev-i386 \
    libncurses5-dev \
    libtool-bin \
    linux-libc-dev \
    make \
    patch \
    s3cmd \
    sed \
    subversion \
    texinfo \
    upx-ucl \
    wget \
    xz-utils

WORKDIR /opt
USER gcc-user

RUN curl -sL http://crosstool-ng.org/download/crosstool-ng/crosstool-ng-1.22.0.tar.xz | tar Jxvf - && \
    cd crosstool-ng && \
    ./configure --enable-local && \
    make -j$(nproc)

COPY build /opt/
