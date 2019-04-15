FROM ubuntu:18.04
MAINTAINER Matt Godbolt <matt@godbolt.org>

# NB wine using artful as there's no bionic repo (yet)
# was: apt-add-repository 'https://dl.winehq.org/wine-builds/ubuntu/' && \
RUN dpkg --add-architecture i386 && apt-get -y update && \
    apt-get install -y curl apt-transport-https apt-utils software-properties-common && \
    curl -sL https://dl.winehq.org/wine-builds/Release.key | apt-key add - && \
    apt-add-repository 'deb https://dl.winehq.org/wine-builds/ubuntu/ artful main' && \
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

RUN apt-get install binutils-multiarch -y
RUN mkdir -p /root
RUN mkdir -p /root/.ssh
COPY known_hosts /root/.ssh/

ENV PATH /opt/compiler-explorer/node/bin:$PATH
RUN useradd gcc-user && mkdir -p /compiler-explorer /home/gcc-user && chown gcc-user /compiler-explorer && chown gcc-user /home/gcc-user
ENV HOME /home/gcc-user

WORKDIR /compiler-explorer
