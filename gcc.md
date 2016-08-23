# GCC building docker image

To build a gcc using the docker image:
$ docker run -v $(pwd):/out mattgodbolt/gcc-builder bash build.sh 6.2.0 /out/gcc-6.2.0.tar.gz
