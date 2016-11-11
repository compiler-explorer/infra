FROM ubuntu:16.04
MAINTAINER Matt Godbolt <matt@godbolt.org>

RUN dpkg --add-architecture i386 && \
    apt-get -y update && \
    apt-get install -y python-software-properties software-properties-common && \
    apt-get -y update && \
    add-apt-repository -y ppa:ubuntu-toolchain-r/test && \
    apt-get -y update && \
    apt-get install -y \
    clang-3.5 \
    curl \
    g++ \
    g++-4.8-powerpc-linux-gnu \
    g++-5-mips-linux-gnu \
    g++-5-mips64-linux-gnuabi64 \
    g++-5-mips64el-linux-gnuabi64 \
    g++-5-mipsel-linux-gnu \
    g++-aarch64-linux-gnu \
    g++-arm-linux-gnueabihf \
    gcc \
    git \
    libboost-all-dev \
    libc6-dev-i386 \
    libc6:i386 \
    libncurses5:i386 \
    libstdc++6:i386 \
    linux-libc-dev \
    make

RUN cd / && curl "https://nodejs.org/dist/v4.2.3/node-v4.2.3-linux-x64.tar.gz" | tar zxf - && mv node-v4.2.3-linux-x64 node

RUN mkdir -p /root
RUN mkdir -p /root/.ssh
COPY known_hosts /root/.ssh/

RUN apt-get autoremove -y
RUN apt-get clean
RUN rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*
# Workaround for my woes with multiarch
RUN ln -s /usr/include/asm-generic /usr/include/asm

# Experimental wine stuff
RUN add-apt-repository -y ppa:wine/wine-builds && \
    apt-get update && \
    apt-get -y install winehq-devel

#####################
RUN useradd gcc-user && mkdir -p /gcc-explorer /home/gcc-user && chown gcc-user /gcc-explorer && chown gcc-user /home/gcc-user
ENV HOME /home/gcc-user
ENV PATH /node/bin:$PATH
COPY *.sh /

USER gcc-user
RUN /update.sh
WORKDIR /gcc-explorer
VOLUME /gcc-explorer
EXPOSE 10240
CMD ["/run.sh"]
