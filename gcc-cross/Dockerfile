FROM ubuntu:18.04
MAINTAINER Matt Godbolt <matt@godbolt.org>

ARG DEBIAN_FRONTEND=noninteractive

RUN mkdir -p /opt mkdir -p /home/gcc-user && useradd gcc-user && chown gcc-user /opt /home/gcc-user

RUN apt-get clean -y && apt-get check -y

RUN apt-get update -y -q && apt-get upgrade -y -q && apt-get upgrade -y -q

RUN apt-get install -y -q \
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
    binutils-multiarch \
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
    wget \
    unzip \
    autopoint \
    gettext \
    xz-utils

WORKDIR /opt
COPY build/patches/cross-tool-ng/cross-tool-ng-1.22.0.patch ./
COPY build/patches/cross-tool-ng/latest-support-k1-mppa.patch ./
RUN curl -sL http://crosstool-ng.org/download/crosstool-ng/crosstool-ng-1.22.0.tar.xz | tar Jxf - && \
    mv crosstool-ng crosstool-ng-1.22.0 && \
    cd crosstool-ng-1.22.0 && \
    patch -p1 < ../cross-tool-ng-1.22.0.patch && \
    ./configure --enable-local && \
    make -j$(nproc)

RUN curl -sL http://crosstool-ng.org/download/crosstool-ng/crosstool-ng-1.23.0.tar.xz | tar Jxf - && \
    cd crosstool-ng-1.23.0 && \
    ./configure --enable-local && \
    make -j$(nproc)

RUN TAG=45a88f046d533df256c1af7b8bcd8b0705f745c5 && \
    curl -sL https://github.com/crosstool-ng/crosstool-ng/archive/${TAG}.zip --output crosstool-ng-master.zip  && \
    unzip crosstool-ng-master.zip && \
    cd crosstool-ng-${TAG} && \
    patch -p1 < ../latest-support-k1-mppa.patch && \
    ./bootstrap && \
    ./configure --prefix=/opt/crosstool-ng-latest && \
    make -j$(nproc) && \
    make install

RUN mkdir -p /opt/.build/tarballs
COPY build /opt/
RUN chown -R gcc-user /opt
USER gcc-user
