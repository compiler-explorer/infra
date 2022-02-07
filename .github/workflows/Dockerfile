FROM ubuntu:20.04

ARG DEBIAN_FRONTEND=noninteractive
RUN apt update -y -q && apt upgrade -y -q && apt update -y -q && \
    apt install -y -q \
    python3 \
    python3.8-venv \
    make \
    squashfs-tools \
    wget

RUN groupadd -g 1000 ubuntu
RUN useradd -ms /bin/bash -u 1000 -g 1000 ubuntu
RUN mkdir /work
RUN chown -R ubuntu:ubuntu /work
USER ubuntu
WORKDIR /work
ENV PATH=$PATH:/work/bin
