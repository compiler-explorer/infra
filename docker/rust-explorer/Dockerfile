FROM mattgodbolt/gcc-explorer:base
MAINTAINER Matt Godbolt <matt@godbolt.org>

RUN apt-get install -y \
	gcc g++

COPY compilers.sh /root/
RUN bash /root/compilers.sh

RUN su -c "cd /gcc-explorer && ls && make prereqs" gcc-user

RUN rm /root/compilers.sh
RUN apt-get purge -y gcc g++ make
RUN /root/cleanup.sh

USER gcc-user
WORKDIR /gcc-explorer
EXPOSE 10242
CMD ["nodejs", "app.js", "--env", "amazon-rust"]
