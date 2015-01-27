FROM compiler-base
MAINTAINER Matt Godbolt <matt@godbolt.org>

RUN apt-get install -y \
    clang \
    g++ \
    g++-4.4 \
    g++-4.5 \
    g++-4.5-arm-linux-gnueabi \
    g++-4.6 \
    g++-4.6-arm-linux-gnueabi \
    g++-4.7 \
    g++-4.7-multilib \
    g++-4.8 \
    g++-4.8-multilib \
    gcc-4.4 \
    gcc-4.5 \
    gcc-4.6 \
    gcc-4.7-base \
    gcc-4.7-multilib \
    gcc-4.8 \
    gcc-4.8-multilib \
    gcc-avr \
    gcc-msp430 \
    gcc-snapshot

COPY compilers.sh /root/
RUN bash /root/compilers.sh
RUN rm /root/compilers.sh && ${CLEANUP_COMMAND}

RUN git clone https://github.com/mattgodbolt/gcc-explorer.git /d-explorer
RUN chown -R gcc-user /d-explorer
RUN su -c "cd /gcc-explorer && ls && make prereqs GDC=/usr/bin/gdc-4.9" gcc-user

USER gcc-user
WORKDIR /d-explorer
VOLUME /d-explorer
EXPOSE 10241
CMD ["nodejs", "app.js", "--env", "amazon-d"]
