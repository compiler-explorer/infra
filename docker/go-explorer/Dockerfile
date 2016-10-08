FROM ubuntu:14.04
MAINTAINER Matt Godbolt <matt@godbolt.org>

RUN apt-get -y update && apt-get install -y python-software-properties software-properties-common
RUN add-apt-repository -y ppa:ubuntu-toolchain-r/test

RUN apt-get -y update && apt-get install -y \
    git \
    make \
    curl \
    golang \
    gccgo

RUN cd / && curl "https://nodejs.org/dist/v4.2.3/node-v4.2.3-linux-x64.tar.gz" | tar zxf - && mv node-v4.2.3-linux-x64 node

RUN mkdir -p /root
RUN mkdir -p /root/.ssh
COPY known_hosts /root/.ssh/

RUN apt-get purge -y openjdk-6-jre-lib
RUN apt-get autoremove -y
RUN apt-get clean
RUN rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

#####################
RUN useradd gcc-user && mkdir -p /gcc-explorer /home/gcc-user && chown gcc-user /gcc-explorer && chown gcc-user /home/gcc-user
ENV HOME /home/gcc-user
ENV PATH /node/bin:$PATH
COPY *.sh /

USER gcc-user
RUN /update.sh
WORKDIR /gcc-explorer
EXPOSE 10243
CMD ["/run.sh"]
