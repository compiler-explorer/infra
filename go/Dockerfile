FROM ubuntu:18.04
MAINTAINER Matt Godbolt <matt@godbolt.org>

ARG DEBIAN_FRONTEND=noninteractive
RUN apt update -y -q && apt upgrade -y -q && apt update -y -q && \
    apt install -y -q \
    curl \
    gcc \
    git \
    s3cmd \
    xz-utils

ARG BOOTSTRAP_VERSION=1.11.2
RUN mkdir -p /root/bootstrap && \
    cd /root/bootstrap && \
    curl -sL https://dl.google.com/go/go${BOOTSTRAP_VERSION}.linux-amd64.tar.gz | tar zxf -
ENV GOROOT_BOOTSTRAP=/root/bootstrap/go

RUN mkdir -p /root
COPY build /root/

WORKDIR /root
