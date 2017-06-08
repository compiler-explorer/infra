FROM mattgodbolt/compiler-explorer:base
MAINTAINER Matt Godbolt <matt@godbolt.org>

# Add nvcc compiler from Nvidia
RUN curl ${http_proxy:+--proxy $http_proxy} http://developer.download.nvidia.com/compute/cuda/repos/ubuntu1604/x86_64/7fa2af80.pub | apt-key add - ; \
    echo 'deb http://developer.download.nvidia.com/compute/cuda/repos/ubuntu1604/x86_64 /' > /etc/apt/sources.list.d/cuda.list ; \
    apt-get update && apt install -y cuda-minimal-build-8-0 ; \
    rm -rf /var/lib/apt/lists/*

COPY *.sh /

USER gcc-user
EXPOSE 10240
CMD ["/run.sh"]
