FROM compiler-base
MAINTAINER Matt Godbolt <matt@godbolt.org>

RUN apt-get install -y \
	gcc g++

COPY compilers.sh /root/
RUN bash /root/compilers.sh

RUN git clone https://github.com/mattgodbolt/gcc-explorer.git /rust-explorer
RUN chown -R gcc-user /rust-explorer
RUN su -c "cd /rust-explorer && ls && make prereqs" gcc-user

RUN echo "rm /root/compilers.sh && apt-get -y purge gcc g++ make && $CLEANUP_COMMAND" > /tmp/cleanup
RUN bash /tmp/cleanup

USER gcc-user
WORKDIR /rust-explorer
VOLUME /rust-explorer
EXPOSE 10242
CMD ["nodejs", "app.js", "--env", "amazon-rust"]
