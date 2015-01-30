#!/bin/bash

set -ex

SUDO=sudo
if [[ $UID = 0 ]]; then
    SUDO=
fi

# TODO:
# check caching works in nginx (seemingly yes for gcc explorer)
# check STH proxy works - it does, but seemingly doesn't cache?
# access.log seems not reliable for bbc

$SUDO docker stop gcc d rust nginx || true
$SUDO docker rm gcc d rust nginx || true

$SUDO docker pull mattgodbolt/gcc-explorer

GCC=$(sudo docker run --name gcc -d -p 10240:10240 mattgodbolt/gcc-explorer:gcc)
D=$(sudo docker run --name d -d -p 10241:10241 mattgodbolt/gcc-explorer:d)
RUST=$(sudo docker run --name rust -d -p 10242:10242 mattgodbolt/gcc-explorer:rust)

trap "$SUDO docker stop $GCC $D $RUST" SIGINT SIGTERM SIGPIPE

$SUDO docker run \
    -p 80:80 \
    --name nginx \
    --volumes-from gcc \
    -v /var/log/nginx:/var/log/nginx \
    -v /home/ubuntu:/var/www \
    -v $(pwd)/nginx:/etc/nginx/sites-enabled \
    --link gcc:gcc --link d:d --link rust:rust \
    dockerfile/nginx
