FROM ubuntu:16.04
MAINTAINER Matt Godbolt <matt@godbolt.org>

RUN dpkg --add-architecture i386 && \
    apt-get -y update && \
    apt-get install -y python-software-properties software-properties-common && \
    apt-get -y update && \
    add-apt-repository -y ppa:wine/wine-builds && \
    add-apt-repository -y ppa:ubuntu-toolchain-r/test && \
    apt-get -y update && \
    apt-get install -y \
        libboost-all-dev \
        libc6-dev-i386 \
        libc6:i386 \
        libncurses5:i386 \
        libstdc++6:i386 \
        linux-libc-dev \
        bzip2 \
        curl \
        winehq-devel \
        g++ \
        git \
        make \
    && \
    apt-get autoremove -y && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/* && \
    ln -s /usr/include/asm-generic /usr/include/asm

RUN mkdir -p /root
RUN mkdir -p /root/.ssh
COPY known_hosts /root/.ssh/

ENV PATH /opt/compiler-explorer/node/bin:$PATH
RUN useradd gcc-user && mkdir -p /compiler-explorer /home/gcc-user && chown gcc-user /compiler-explorer && chown gcc-user /home/gcc-user
ENV HOME /home/gcc-user

WORKDIR /compiler-explorer
