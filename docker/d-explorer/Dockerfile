FROM frolvlad/alpine-glibc
MAINTAINER Matt Godbolt <matt@godbolt.org>

RUN apk add --no-cache \
    bash \
    bzip2 \
    curl \
    gcc \
    git \
    libc-dev \
    make \
    nodejs \
    tar \
    xz

RUN cd / && curl -L https://github.com/sgerrand/docker-glibc-builder/releases/download/2.23-0/glibc-bin-2.23-0-x86_64.tar.gz | tar zxvf - --wildcards usr/glibc-compat/lib/*.a

RUN mkdir -p /root
RUN mkdir -p /root/.ssh
COPY .s3cfg /root/
COPY known_hosts /root/.ssh/
COPY compilers.sh /root/
RUN bash /root/compilers.sh
RUN rm /root/compilers.sh
RUN rm /root/.s3cfg

#####################
RUN adduser -D gcc-user && mkdir -p /gcc-explorer /home/gcc-user && chown gcc-user /gcc-explorer && chown gcc-user /home/gcc-user
ENV HOME /home/gcc-user
ENV PATH /opt/node/bin:$PATH
COPY package.json /tmp/
RUN su gcc-user bash -c "cd /tmp; env PATH=/opt/node/bin:$PATH npm install"
COPY run.sh /

USER gcc-user
WORKDIR /gcc-explorer
EXPOSE 10241
CMD ["/run.sh"]
