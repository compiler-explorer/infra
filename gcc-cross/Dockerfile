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
    xz-utils \
    git \
    python-dev \
    unzip

WORKDIR /opt
RUN curl -sL http://crosstool-ng.org/download/crosstool-ng/crosstool-ng-1.23.0.tar.xz | tar Jxf - && \
    cd crosstool-ng-1.23.0 && \
    ./configure --enable-local && \
    make -j$(nproc)

RUN git clone https://github.com/crosstool-ng/crosstool-ng && \
    cd crosstool-ng && \
    ./bootstrap && \
    ./configure --enable-local && \
    make -j$(nproc)

COPY build /opt/
RUN chown -R gcc-user /opt
USER gcc-user
