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

ALL="nginx gcc gcc1204 d rust"
$SUDO docker stop ${ALL} || true
$SUDO docker rm ${ALL} || true

CFG="-v ${CONFIG_FILE}:/site.sh:ro"

# Terrible hack as I can't for the life of me get the containers to reliably start:
# sometimes they hang or get stuck in npm update due to a as-yet-undiscovered race/problem.
start_and_wait() {
    local NAME=$1
    local PORT=$2
    shift
    shift
    local FULL_COMMAND="${SUDO} docker run --name ${NAME} ${CFG} -d -p ${PORT}:${PORT} $* mattgodbolt/gcc-explorer:${NAME}"
    local CONTAINER_UID=""
    for retries in $(seq 3); do
        $SUDO docker stop ${NAME} || true
        $SUDO docker rm ${NAME} || true
        echo "Attempt ${retries} to start ${NAME}"
        CONTAINER_UID=$($FULL_COMMAND)
        for second in $(seq 60); do
            sleep 1
            if ! $SUDO docker ps -q --no-trunc | grep ${CONTAINER_UID}; then
                echo "Container failed to start, logs:"
                $SUDO docker logs ${NAME}
                break
            fi
            if curl http://localhost:$PORT/ > /dev/null 2>&1; then
                echo "Server ${NAME} is up and running"
                return
            fi
        done
        echo "Failed."
    done
}

trap "$SUDO docker stop ${ALL}" SIGINT SIGTERM SIGPIPE

start_and_wait gcc1204 20480
start_and_wait gcc 10240 --link gcc1204:gcc1204
start_and_wait d 10241
start_and_wait rust 10242

$SUDO docker run \
    -p ${EXTERNAL_PORT}:80 \
    --name nginx \
    --volumes-from gcc \
    -v /var/log/nginx:/var/log/nginx \
    -v /home/ubuntu:/var/www:ro \
    -v $(pwd)/nginx:/etc/nginx/sites-enabled:ro \
    --link gcc:gcc --link d:d --link rust:rust \
    dockerfile/nginx
