FROM ubuntu:12.04
MAINTAINER Matt Godbolt <matt@godbolt.org>

RUN apt-get -y update && apt-get install -y python-software-properties
RUN add-apt-repository -y ppa:chris-lea/node.js && add-apt-repository -y ppa:ubuntu-toolchain-r/test

RUN apt-get -y update && apt-get install -y \
    curl \
    git \
    make \
    nodejs \
    s3cmd \
    clang \
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
    gcc-4.7-base \
    gcc-4.7-multilib \
    gcc-4.8 \
    gcc-4.8-multilib \
    gcc-avr \
    gcc-msp430 \
    gcc-snapshot

RUN mkdir -p /root
RUN mkdir -p /root/.ssh
COPY .s3cfg /root/
COPY known_hosts /root/.ssh/
COPY compilers.sh /root/
RUN bash /root/compilers.sh
RUN rm /root/compilers.sh
RUN rm /root/.s3cfg
RUN apt-get purge -y curl s3cmd openjdk-6-jre-lib
RUN apt-get autoremove -y
RUN apt-get clean
RUN rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

#####################
RUN useradd gcc-user && mkdir -p /gcc-explorer /home/gcc-user && chown gcc-user /gcc-explorer && chown gcc-user /home/gcc-user
ENV HOME /home/gcc-user
COPY run.sh /

USER gcc-user
WORKDIR /gcc-explorer
VOLUME /gcc-explorer
EXPOSE 10240
CMD ["/run.sh"]
