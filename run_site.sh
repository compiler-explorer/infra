#!/bin/bash

set -ex

DIR=$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )
SUDO=sudo
if [[ $UID = 0 ]]; then
    SUDO=
fi

EXTERNAL_PORT=80
CONFIG_FILE=${DIR}/site-prod.sh
if [[ ${DEV_MODE=1} = 1 ]]; then
    EXTERNAL_PORT=8000
    CONFIG_FILE=${DIR}/site-dev.sh
else
    $SUDO docker pull mattgodbolt/gcc-explorer
fi

ALL="gcc gcc1204 d rust nginx"
$SUDO docker stop ${ALL} || true
$SUDO docker rm ${ALL} || true

CFG="-v ${CONFIG_FILE}:/site.sh:ro"

$SUDO docker run --name gcc1204 ${CFG} -d -p 20480:20480 mattgodbolt/gcc-explorer:gcc1204
sleep 10
$SUDO docker run --name gcc ${CFG} --link gcc1204:gcc1204 -d -p 10240:10240 mattgodbolt/gcc-explorer:gcc
sleep 10
$SUDO docker run --name d ${CFG} -d -p 10241:10241 mattgodbolt/gcc-explorer:d
sleep 10
$SUDO docker run --name rust ${CFG} -d -p 10242:10242 mattgodbolt/gcc-explorer:rust

trap "$SUDO docker stop ${ALL}" SIGINT SIGTERM SIGPIPE

$SUDO docker run \
    -p ${EXTERNAL_PORT}:80 \
    --name nginx \
    --volumes-from gcc \
    -v /var/log/nginx:/var/log/nginx \
    -v /home/ubuntu:/var/www:ro \
    -v $(pwd)/nginx:/etc/nginx/sites-enabled:ro \
    --link gcc:gcc --link d:d --link rust:rust \
    dockerfile/nginx
