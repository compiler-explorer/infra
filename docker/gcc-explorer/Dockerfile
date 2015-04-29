FROM ubuntu:14.04
MAINTAINER Matt Godbolt <matt@godbolt.org>

RUN apt-get -y update && apt-get install -y python-software-properties software-properties-common
RUN add-apt-repository -y ppa:chris-lea/node.js && add-apt-repository -y ppa:ubuntu-toolchain-r/test

RUN apt-get -y update && apt-get install -y \
    curl \
    git \
    make \
    nodejs \
    s3cmd \
    clang-3.5 \
    gcc \
    g++ \
    g++-4.8 \
    g++-4.9 \
    g++-4.8-powerpc-linux-gnu \
    g++-arm-linux-gnueabihf \
    g++-aarch64-linux-gnu

RUN mkdir -p /root
RUN mkdir -p /root/.ssh
COPY .s3cfg /root/
COPY known_hosts /root/.ssh/
COPY compilers.sh /root/
RUN bash /root/compilers.sh

COPY clang.list /etc/apt/sources.list.d/
RUN sudo add-apt-repository ppa:xorg-edgers/ppa 
RUN apt-get -y update
RUN curl http://llvm.org/apt/llvm-snapshot.gpg.key | sudo apt-key add -
RUN apt-key adv --keyserver keyserver.ubuntu.com --recv-keys 15CF4D18AF4F7421
RUN apt-get install --force-yes -y clang-3.6 clang-3.7

RUN rm /root/compilers.sh
RUN rm /root/.s3cfg
RUN apt-get purge -y curl s3cmd openjdk-6-jre-lib
RUN apt-get autoremove -y
RUN apt-get clean
RUN rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

#####################
RUN useradd gcc-user && mkdir -p /gcc-explorer /home/gcc-user && chown gcc-user /gcc-explorer && chown gcc-user /home/gcc-user
ENV HOME /home/gcc-user
COPY package.json /tmp/
RUN su gcc-user bash -c "cd /tmp; npm install"
COPY run.sh /

USER gcc-user
WORKDIR /gcc-explorer
VOLUME /gcc-explorer
EXPOSE 10240
CMD ["/run.sh"]
