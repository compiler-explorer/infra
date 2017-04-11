FROM ubuntu:16.04
MAINTAINER Matt Godbolt <matt@godbolt.org>

RUN apt-get -y update && apt-get install -y \
    sudo \
    libboost-all

#####################
RUN useradd ce-user && mkdir /home/ce-user && chown ce-user /home/ce-user
ENV HOME /home/ce-user
COPY run.sh /
WORKDIR /home/ce-user
ENTRYPOINT ["/run.sh"]
