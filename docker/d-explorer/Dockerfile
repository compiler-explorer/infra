FROM mattgodbolt/gcc-explorer:base
MAINTAINER Matt Godbolt <matt@godbolt.org>

RUN apt-get install -y \
    gcc \
    gdc \
    gdc-4.4 \
    gdc-4.6 \
    gdc-4.8 \
    gdc-4.9

COPY compilers.sh /root/
RUN bash /root/compilers.sh

RUN su -c "cd /gcc-explorer && ls && make prereqs GDC=/usr/bin/gdc-4.9" gcc-user

RUN echo "rm /root/compilers.sh && apt-get purge -y gcc && $CLEANUP_COMMAND" > /tmp/cleanup
RUN bash /tmp/cleanup

USER gcc-user
WORKDIR /gcc-explorer
EXPOSE 10241
CMD ["nodejs", "app.js", "--env", "amazon-d"]
