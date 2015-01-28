FROM mattgodbolt/gcc-explorer:base
MAINTAINER Matt Godbolt <matt@godbolt.org>

RUN apt-get install -y \
	gcc g++

COPY compilers.sh /root/
RUN bash /root/compilers.sh

RUN su -c "cd /gcc-explorer && ls && make prereqs" gcc-user

RUN echo "rm /root/compilers.sh && apt-get -y purge gcc g++ make && $CLEANUP_COMMAND" > /tmp/cleanup
RUN bash /tmp/cleanup

USER gcc-user
WORKDIR /gcc-explorer
VOLUME /gcc-explorer
EXPOSE 10242
CMD ["nodejs", "app.js", "--env", "amazon-rust"]
