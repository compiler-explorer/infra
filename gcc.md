# GCC building docker image

To build a gcc using the docker image:

    docker run -v $(pwd):/out mattgodbolt/gcc-builder bash build.sh 6.2.0 /out/gcc-6.2.0.tar.gz

Note you'll need lots of disk space (32GB+).

If like me, you want to run on a RancherOS EC2 image, you'll need to do something like:

    docker run --privileged -i --rm ubuntu bash << EOF
    apt-get update
    apt-get install -y cloud-guest-utils parted
    growpart /dev/xvda 1
    partprobe
    resize2fs /dev/xvda1
    EOF

...to ensure the RancherOS partition uses all available space.
