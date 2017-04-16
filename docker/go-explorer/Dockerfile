FROM mattgodbolt/compiler-explorer:base
MAINTAINER Matt Godbolt <matt@godbolt.org>

COPY *.sh /

USER gcc-user
EXPOSE 10243
CMD ["/run.sh"]
