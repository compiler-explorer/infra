FROM compiler-base
MAINTAINER Matt Godbolt <matt@godbolt.org>

RUN apt-get install -y \
    gdc \
    gdc-4.4 \
    gdc-4.6 \
    gdc-4.8 \
    gdc-4.9


COPY compilers.sh /root/
RUN bash /root/compilers.sh
RUN rm /root/compilers.sh && $CLEANUP_COMMAND

RUN git clone https://github.com/mattgodbolt/gcc-explorer.git /gcc-explorer
RUN chown -R gcc-user /gcc-explorer
RUN su -c "cd /gcc-explorer && ls && make prereqs" gcc-user

USER gcc-user
WORKDIR /gcc-explorer
VOLUME /gcc-explorer
EXPOSE 10240
CMD ["nodejs", "app.js", "--env", "amazon"]
