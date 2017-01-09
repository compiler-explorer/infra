# ubuntu 12.04 to be the most compatible with whatever's
# built from CE
FROM ubuntu:12.04
MAINTAINER Matt Godbolt <matt@godbolt.org>

RUN apt-get -y update && apt-get install -y \
    sudo \
    libboost-all-dev

#####################
RUN useradd ce-user && mkdir /home/ce-user && chown ce-user /home/ce-user
ENV HOME /home/ce-user
COPY run.sh /
WORKDIR /home/ce-user
ENTRYPOINT ["/run.sh"]
