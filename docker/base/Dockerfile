FROM ubuntu:16.04
MAINTAINER Matt Godbolt <matt@godbolt.org>

RUN dpkg --add-architecture i386 && \
    apt-get -y update && \
    apt-get install -y python-software-properties software-properties-common && \
    apt-get -y update && \
    add-apt-repository -y ppa:ubuntu-toolchain-r/test && \
    apt-get -y update && \
    apt-get install -y \
    bzip2 \
    curl \
    g++ \
    git \
    make

RUN mkdir -p /root
RUN mkdir -p /root/.ssh
COPY known_hosts /root/.ssh/

ENV PATH /opt/gcc-explorer/node/bin:$PATH
RUN useradd gcc-user && mkdir -p /gcc-explorer /home/gcc-user && chown gcc-user /gcc-explorer && chown gcc-user /home/gcc-user
ENV HOME /home/gcc-user

WORKDIR /gcc-explorer
