FROM ubuntu:20.04

ARG DEBIAN_FRONTEND=noninteractive
RUN apt update -y -q && apt upgrade -y -q && apt update -y -q && \
    apt install -y -q \
    python3 \
    python3.8-venv \
    make \
    squashfs-tools \
    wget


WORKDIR /root
ENV PATH=$PATH:/root/bin
