FROM ubuntu:12.04
MAINTAINER Matt Godbolt <matt@godbolt.org>

RUN mkdir -p /opt
RUN useradd gcc-user && mkdir /home/gcc-user && chown gcc-user /home/gcc-user
RUN apt-get -y update && apt-get install -y python-software-properties
RUN add-apt-repository -y ppa:chris-lea/node.js && add-apt-repository -y ppa:ubuntu-toolchain-r/test

RUN apt-get -y update && apt-get install -y \
    curl \
    s3cmd \
    git \
    make \
    nodejs

RUN mkdir -p /opt
RUN mkdir -p /root
COPY .s3cfg /root/
RUN mkdir -p /root/.ssh
COPY known_hosts /root/.ssh/

ENV CLEANUP_COMMAND rm /root/.s3cfg && apt-get purge -y curl s3cmd openjdk-6-jre-lib \
    && apt-get autoremove -y && apt-get clean && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*
