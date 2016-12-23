FROM mattgodbolt/gcc-explorer:base
MAINTAINER Matt Godbolt <matt@godbolt.org>

RUN apt-get autoremove -y
RUN apt-get clean
RUN rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

#####################
COPY *.sh /

USER gcc-user
EXPOSE 10242
CMD ["/run.sh"]
