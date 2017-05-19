FROM ubuntu:16.04
MAINTAINER Matt Godbolt <matt@godbolt.org>

RUN  dpkg --add-architecture i386 && apt-get -y update && \
    apt-get install -y curl apt-transport-https apt-utils software-properties-common && \
    apt-add-repository 'https://dl.winehq.org/wine-builds/ubuntu/' && \
    curl -sL https://repos.wine-staging.com/wine/Release.key | apt-key add - && \
    apt-get -y update && \
    apt-get install -y \
        bzip2 \
        libc6-dev-i386 \
        make \
        git \
    && apt-get install -y --install-recommends winehq-devel && \
    apt-get autoremove -y && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/* && \
    ln -s /usr/include/asm-generic /usr/include/asm

# Add Advance Toolchain from IBM - prebuilt ppc64{,le} cross-compiler based on gcc
# curl - account for proxy if set.
RUN curl ${http_proxy:+--proxy $http_proxy} http://ftp.unicamp.br/pub/linuxpatch/toolchain/at/ubuntu/dists/utopic/6976a827.gpg.key | apt-key add -
RUN echo 'deb http://ftp.unicamp.br/pub/linuxpatch/toolchain/at/ubuntu xenial at10.0'  >> /etc/apt/sources.list.d/at.list
RUN apt update && \
    apt install -y advance-toolchain-at10.0-cross-ppc64 advance-toolchain-at10.0-cross-ppc64le && \
    rm -rf /var/lib/apt/lists/*

RUN mkdir -p /root
RUN mkdir -p /root/.ssh
COPY known_hosts /root/.ssh/

ENV PATH /opt/compiler-explorer/node/bin:$PATH
RUN useradd gcc-user && mkdir -p /compiler-explorer /home/gcc-user && chown gcc-user /compiler-explorer && chown gcc-user /home/gcc-user
ENV HOME /home/gcc-user

WORKDIR /compiler-explorer
