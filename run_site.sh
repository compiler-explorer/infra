#!/bin/bash

set -ex

DIR=$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )
SUDO=sudo
if [[ $UID = 0 ]]; then
    SUDO=
fi

if [[ -f /env ]]; then
    source /env
fi

DEV_MODE=$1
if [[ "x${DEV_MODE}x" = "xx" ]]; then
    DEV_MODE="dev"
fi

EXTERNAL_PORT=80
CONFIG_FILE=${DIR}/site-prod.sh
if [[ "${DEV_MODE}" != "prod" ]]; then
    EXTERNAL_PORT=8000
    CONFIG_FILE=${DIR}/site-${DEV_MODE}.sh
else
    $SUDO docker pull -a mattgodbolt/gcc-explorer
fi

ALL="nginx gcc go gcc1204 dx rust"
$SUDO docker stop ${ALL} || true
$SUDO docker rm ${ALL} || true

CFG="-v ${CONFIG_FILE}:/site.sh:ro"

start_container() {
    local NAME=$1
    local PORT=$2
    shift
    shift
    local TAG=${NAME}
    if [[ "${#NAME}" -eq 1 ]]; then
    	NAME="${NAME}x"
    fi
    local FULL_COMMAND="${SUDO} docker run --name ${NAME} -e GOOGLE_API_KEY=${GOOGLE_API_KEY} ${CFG} -d -v/opt/gcc-explorer:/opt/gcc-explorer:ro -p ${PORT}:${PORT} $* mattgodbolt/gcc-explorer:${TAG}"
    local CONTAINER_UID=""
    $SUDO docker stop ${NAME} >&2 || true
    $SUDO docker rm ${NAME} >&2 || true
    CONTAINER_UID=$($FULL_COMMAND)
    echo ${CONTAINER_UID}
}

wait_for_container() {
    local CONTAINER_UID=$1
    local NAME=$2
    local PORT=$3
    shift
    shift
    shift
    for tensecond in $(seq 15); do
        if ! $SUDO docker ps -q --no-trunc | grep ${CONTAINER_UID}; then
            echo "Container failed to start, logs:"
            $SUDO docker logs ${NAME}
            break
        fi
        if curl http://localhost:$PORT/ > /dev/null 2>&1; then
            echo "Server ${NAME} is up and running"
            return
        fi
        sleep 10
    done
    echo "Failed."
    $SUDO docker logs ${NAME}
}

trap "$SUDO docker stop ${ALL}" SIGINT SIGTERM SIGPIPE

UID_GCC1204=$(start_container gcc1204 20480)
UID_GCC=$(start_container gcc 10240 --link gcc1204:gcc1204)
UID_D=$(start_container d 10241)
UID_RUST=$(start_container rust 10242)
UID_GO=$(start_container go 10243)

wait_for_container ${UID_GCC1204} gcc1204 20480
wait_for_container ${UID_GCC} gcc 10240
wait_for_container ${UID_D} d 10241
wait_for_container ${UID_RUST} rust 10242
wait_for_container ${UID_GO} go 10243

$SUDO docker run \
    -p ${EXTERNAL_PORT}:80 \
    --name nginx \
    --volumes-from gcc \
    -v /var/log/nginx:/var/log/nginx \
    -v /home/ubuntu:/var/www:ro \
    -v $(pwd)/nginx.conf:/etc/nginx/nginx.conf:ro \
    -v $(pwd)/nginx:/etc/nginx/sites-enabled:ro \
    --link gcc:gcc --link dx:d --link rust:rust --link go:go \
    nginx
