FROM mattgodbolt/gcc-explorer:base
MAINTAINER Matt Godbolt <matt@godbolt.org>

RUN apt-get install -y \
    g++-4.8-powerpc-linux-gnu \
    g++-5-mips-linux-gnu \
    g++-5-mips64-linux-gnuabi64 \
    g++-5-mips64el-linux-gnuabi64 \
    g++-5-mipsel-linux-gnu \
    g++-aarch64-linux-gnu \
    g++-arm-linux-gnueabihf \
    git \
    libboost-all-dev \
    libc6-dev-i386 \
    libc6:i386 \
    libncurses5:i386 \
    libstdc++6:i386 \
    linux-libc-dev

RUN apt-get autoremove -y
RUN apt-get clean
RUN rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*
# Workaround for my woes with multiarch
RUN ln -s /usr/include/asm-generic /usr/include/asm

# Experimental wine stuff
RUN add-apt-repository -y ppa:wine/wine-builds && \
    apt-get update && \
    apt-get -y install winehq-devel && echo only here to defeat cache

#####################
COPY *.sh /

USER gcc-user
EXPOSE 10240
CMD ["/run.sh"]
