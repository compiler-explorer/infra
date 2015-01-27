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
RUN echo "rm /root/compilers.sh && $CLEANUP_COMMAND" > /tmp/cleanup
RUN bash /tmp/cleanup

RUN git clone https://github.com/mattgodbolt/gcc-explorer.git /gcc-explorer
RUN chown -R gcc-user /gcc-explorer
RUN su -c "cd /gcc-explorer && ls && make prereqs" gcc-user

USER gcc-user
WORKDIR /gcc-explorer
VOLUME /gcc-explorer
EXPOSE 10240
CMD ["nodejs", "app.js", "--env", "amazon"]
