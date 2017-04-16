FROM mattgodbolt/compiler-explorer:base
MAINTAINER Matt Godbolt <matt@godbolt.org>

COPY *.sh /

USER gcc-user
EXPOSE 10242
CMD ["/run.sh"]
