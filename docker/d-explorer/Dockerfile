FROM mattgodbolt/gcc-explorer:base
MAINTAINER Matt Godbolt <matt@godbolt.org>

COPY *.sh /

USER gcc-user
EXPOSE 10241
CMD ["/run.sh"]
