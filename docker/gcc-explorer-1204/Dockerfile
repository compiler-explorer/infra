FROM ubuntu:12.04
MAINTAINER Matt Godbolt <matt@godbolt.org>

RUN apt-get -y update && apt-get install -y python-software-properties
RUN add-apt-repository -y ppa:ubuntu-toolchain-r/test

RUN apt-get -y update && apt-get install -y \
    libboost-all-dev \
    git \
    make \
    clang \
    curl \
    g++ \
    g++-4.4 \
    g++-4.5 \
    g++-4.5-arm-linux-gnueabi \
    g++-4.6 \
    g++-4.6-arm-linux-gnueabi \
    g++-4.7 \
    g++-4.7-multilib \
    g++-4.8 \
    g++-4.8-multilib \
    gcc-4.4 \
    gcc-4.5 \
    gcc-4.6 \
    gcc-avr \
    gcc-msp430

RUN mkdir -p /root
RUN mkdir -p /root/.ssh
COPY known_hosts /root/.ssh/
RUN apt-get purge -y openjdk-6-jre-lib
RUN apt-get autoremove -y
RUN apt-get clean
RUN rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

#####################
RUN useradd gcc-user && mkdir -p /compiler-explorer /home/gcc-user && chown gcc-user /compiler-explorer && chown gcc-user /home/gcc-user
ENV HOME /home/gcc-user
ENV PATH /opt/compiler-explorer/node/bin:$PATH

COPY *.sh /

USER gcc-user
WORKDIR /compiler-explorer
EXPOSE 20480
CMD ["/run.sh"]
