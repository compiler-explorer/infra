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

RUN cd / && curl "https://nodejs.org/dist/v4.2.3/node-v4.2.3-linux-x64.tar.gz" | tar zxf - && mv node-v4.2.3-linux-x64 node

RUN mkdir -p /root
RUN mkdir -p /root/.ssh
COPY known_hosts /root/.ssh/
