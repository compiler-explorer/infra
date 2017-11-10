FROM ubuntu:17.10
MAINTAINER Matt Godbolt <matt@godbolt.org>

RUN apt update -y && apt upgrade -y
RUN apt install -y \
     awscli \
     bash \
     bzip2 \
     curl \
     git \
     nfs-common \
     python-pip \
     tar \
     upx-ucl \
     xz-utils

COPY *.sh /
COPY *.py /
COPY common.inc /
