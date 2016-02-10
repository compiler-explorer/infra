FROM ubuntu:14.04
MAINTAINER Matt Godbolt <matt@godbolt.org>

RUN apt-get -y update && apt-get install -y python-software-properties software-properties-common
RUN add-apt-repository -y ppa:ubuntu-toolchain-r/test

RUN apt-get -y update && apt-get install -y \
    libc6-dev-i386 \
    linux-libc-dev \
    curl \
    git \
    make \
    s3cmd \
    clang-3.5 \
    gcc \
    g++ \
    g++-4.8 \
    g++-4.9 \
    g++-4.8-powerpc-linux-gnu \
    g++-arm-linux-gnueabihf \
    g++-aarch64-linux-gnu \
    tcc

RUN apt-get install -y \
    libboost-all-dev

RUN mkdir -p /opt && cd /opt && curl "https://nodejs.org/dist/v4.2.3/node-v4.2.3-linux-x64.tar.gz" | tar zxf - && mv node-v4.2.3-linux-x64 node

RUN mkdir -p /root
RUN mkdir -p /root/.ssh
COPY .s3cfg /root/
COPY known_hosts /root/.ssh/
COPY compilers.sh /root/
RUN bash /root/compilers.sh

RUN rm /root/compilers.sh
RUN rm /root/.s3cfg
RUN apt-get purge -y curl s3cmd openjdk-6-jre-lib
RUN apt-get autoremove -y
RUN apt-get clean
RUN rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*
# Workaround for my woes with multiarch
RUN ln -s /usr/include/asm-generic /usr/include/asm

#####################
RUN useradd gcc-user && mkdir -p /gcc-explorer /home/gcc-user && chown gcc-user /gcc-explorer && chown gcc-user /home/gcc-user
ENV HOME /home/gcc-user
ENV PATH /opt/node/bin:$PATH
COPY package.json /tmp/
RUN su gcc-user bash -c "cd /tmp; env PATH=/opt/node/bin:$PATH npm install"
COPY run.sh /

USER gcc-user
WORKDIR /gcc-explorer
VOLUME /gcc-explorer
EXPOSE 10240
CMD ["/run.sh"]
