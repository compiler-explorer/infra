FROM ubuntu:12.04
MAINTAINER Matt Godbolt <matt@godbolt.org>

RUN mkdir -p /opt
RUN useradd gcc-user && mkdir /home/gcc-user && chown gcc-user /home/gcc-user
RUN apt-get -y update && apt-get install -y python-software-properties
RUN add-apt-repository -y ppa:chris-lea/node.js && add-apt-repository -y ppa:ubuntu-toolchain-r/test

RUN apt-get -y update && apt-get install -y \
    curl \
    s3cmd \
    make \
    nodejs

RUN mkdir -p /opt
RUN mkdir -p /root
COPY .s3cfg /root/
RUN mkdir -p /root/.ssh
COPY known_hosts /root/.ssh/
COPY gcc-explorer /gcc-explorer
RUN chown -R gcc-user /gcc-explorer

COPY cleanup.sh /root/
