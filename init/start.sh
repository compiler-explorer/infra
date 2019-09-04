#!/bin/bash

set -ex

ENV=$(curl -sf http://169.254.169.254/latest/user-data || true)
ENV=${ENV:-prod}
CE_USER=ubuntu
DEPLOY_DIR=${PWD}/.deploy

echo Running in environment ${ENV}
source "${PWD}/site-${ENV}.sh"

get_conf() {
    aws ssm get-parameter --name $1 | jq -r .Parameter.Value
}

mount_opt() {
    mkdir -p /opt/compiler-explorer
    mount --bind /efs/compiler-explorer /opt/compiler-explorer
    mkdir -p /opt/intel
    mount --bind /efs/intel /opt/intel
    touch /opt/.health
    mount --bind /efs/.health /opt/.health
}

rsync_boost() {
    echo rsyncing boost libraries
    mkdir -p /celibs
    chown ${CE_USER}:${CE_USER} /celibs
    rsync -a --chown=${CE_USER}:${CE_USER} --exclude=.git /opt/compiler-explorer/libs/boost_* /celibs/ &
}

get_released_code() {
    local DEST=$1
    local S3_KEY=$2
    local URL=https://s3.amazonaws.com/compiler-explorer/${S3_KEY}
    echo "Unpacking build from ${URL}"
    mkdir -p "${DEST}"
    pushd "${DEST}"
    echo ${S3_KEY} >s3_key
    curl -sL "${URL}" | tar Jxf -
    chown -R ${CE_USER}:${CE_USER} .
    popd
}

update_code() {
    local S3_KEY=$(curl -sL https://s3.amazonaws.com/compiler-explorer/version/${BRANCH})
    local CUR_S3_KEY=""
    if [[ -f "${DEPLOY_DIR}/s3_key" ]]; then
        CUR_S3_KEY=$(cat "${DEPLOY_DIR}/s3_key")
    fi

    if [[ "${S3_KEY}" == "${CUR_S3_KEY}" ]]; then
        echo "Build ${S3_KEY} already checked out"
    else
        rm -rf "${DEPLOY_DIR}"
        get_released_code "${DEPLOY_DIR}" "${S3_KEY}"
    fi
}

LOG_DEST_HOST=$(get_conf /compiler-explorer/logDestHost)
LOG_DEST_PORT=$(get_conf /compiler-explorer/logDestPort)

cgcreate -a ubuntu:ubuntu -g memory,pids,cpu,net_cls:ce-sandbox
cgcreate -a ubuntu:ubuntu -g memory,pids,cpu,net_cls:ce-compile

mount_opt
rsync_boost
update_code

cd "${DEPLOY_DIR}"
exec sudo -u ${CE_USER} -H -- \
    /opt/compiler-explorer/node/bin/node \
    -- app.js \
    --suppressConsoleLog \
    --logHost ${LOG_DEST_HOST} \
    --logPort ${LOG_DEST_PORT} \
    --env amazon \
    --port 10240 \
    --static out/dist \
    ${EXTRA_ARGS}
