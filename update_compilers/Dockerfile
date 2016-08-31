FROM alpine:latest
MAINTAINER Matt Godbolt <matt@godbolt.org>

RUN apk add --no-cache nfs-utils bash coreutils py-pip xz curl tar && \
    pip install s3cmd

COPY install_compilers.sh /
COPY efs_update.sh /
