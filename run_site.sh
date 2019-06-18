#!/bin/bash

set -ex

DIR=$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )
DEPLOY_DIR=${DIR}/.deploy
SUDO=sudo
if [[ $UID = 0 ]]; then
    SUDO=
fi

DEV_MODE=$1
if [[ "x${DEV_MODE}x" = "xx" ]]; then
    DEV_MODE="dev"
fi

CONTAINER_SUFFIX=""
EXTERNAL_PORT=80
CONFIG_FILE=${DIR}/site-prod.sh
CE_USER=ubuntu
if [[ "${DEV_MODE}" != "prod" ]]; then
    EXTERNAL_PORT=7000
    CONFIG_FILE=${DIR}/site-${DEV_MODE}.sh
fi
. ${CONFIG_FILE}

rsync_boost() {
    echo rsyncing boost libraries
    ${SUDO} mkdir -p /celibs
    ${SUDO} chown ${CE_USER}:${CE_USER} /celibs
    ${SUDO} rsync -a --chown=${CE_USER}:${CE_USER} --exclude=.git /opt/compiler-explorer/libs/boost_* /celibs/ &
}

rsync_boost

get_released_code() {
    local S3_KEY=$(curl -sL https://s3.amazonaws.com/compiler-explorer/version/${BRANCH})
    local URL=https://s3.amazonaws.com/compiler-explorer/${S3_KEY}
    echo "Unpacking build from ${URL}"
    mkdir -p $1
    pushd $1
    echo ${S3_KEY} > s3_key
    curl -sL ${URL} | tar Jxf -
    if [[ $UID = 0 ]]; then
        chown -R ${CE_USER} .
    fi
    popd
}

update_code() {
    rm -rf ${DEPLOY_DIR}
    get_released_code ${DEPLOY_DIR}
}

update_code

get_conf() {
    aws ssm get-parameter --name $1 | jq -r .Parameter.Value
}

LOG_DEST_HOST=$(get_conf /compiler-explorer/logDestHost)
LOG_DEST_PORT=$(get_conf /compiler-explorer/logDestPort)

# TODO: remove the `which` once we move to a new distro that has it built in
which cgcreate && cgcreate -a ubuntu:ubuntu -g memory,pids,cpu,net_cls:ce-sandbox

cd ${DEPLOY_DIR} && \
    sudo -u ${CE_USER} -H -- \
    /opt/compiler-explorer/node/bin/node \
    -- app.js \
    --suppressConsoleLog --logHost ${LOG_DEST_HOST} --logPort ${LOG_DEST_PORT} \
    --env amazon --port 10240 --static out/dist \
    ${EXTRA_ARGS}
