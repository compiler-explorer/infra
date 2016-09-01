FROM frolvlad/alpine-glibc
MAINTAINER Matt Godbolt <matt@godbolt.org>

RUN apk add --no-cache nfs-utils bash coreutils py-pip xz curl tar bzip2 findutils binutils && \
    pip install s3cmd && \
    cd /bin && curl http://upx.sourceforge.net/download/upx-3.91-amd64_linux.tar.bz2 | \
        tar jxf - --wildcards '*/upx' --strip-components 1

COPY install_compilers.sh /
COPY efs_update.sh /
