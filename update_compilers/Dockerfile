FROM ubuntu:16.04
MAINTAINER Matt Godbolt <matt@godbolt.org>

RUN apt update -y && apt upgrade -y
RUN apt install -y \
     awscli \
     bash \
     bzip2 \
     curl \
     nfs-common \
     python-pip \
     tar \
     upx-ucl \
     xz-utils

COPY install_compilers.sh /
COPY efs_update.sh /
