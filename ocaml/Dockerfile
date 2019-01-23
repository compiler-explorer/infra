FROM ubuntu:18.04
MAINTAINER Matt Godbolt <matt@godbolt.org>

ARG DEBIAN_FRONTEND=noninteractive
RUN apt update -y -q && apt upgrade -y -q && apt update -y -q && \
    apt install -y -q \
    curl \
    gcc \
    git \
    make \
    s3cmd \
    xz-utils

RUN mkdir -p /root
COPY build /root/

WORKDIR /root
