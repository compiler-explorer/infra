FROM busybox:glibc
MAINTAINER Matt Godbolt <matt@godbolt.org>

RUN echo "ce-user:x:100:100:ce-user:/home/ce-user:/bin/sh" >> /etc/passwd
RUN mkdir /home/ce-user && chown ce-user /home/ce-user
ENV HOME /home/ce-user
WORKDIR /home/ce-user
USER ce-user
