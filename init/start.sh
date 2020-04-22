#!/bin/bash

set -ex

ENV=$(curl -sf http://169.254.169.254/latest/user-data || true)
ENV=${ENV:-prod}
CE_USER=ubuntu
DEPLOY_DIR=${PWD}/.deploy

echo Running in environment "${ENV}"
# shellcheck disable=SC1090
source "${PWD}/site-${ENV}.sh"

get_conf() {
    aws ssm get-parameter --name "$1" | jq -r .Parameter.Value
}

mount_opt() {
    mkdir -p /opt/compiler-explorer
    mountpoint /opt/compiler-explorer || mount --bind /efs/compiler-explorer /opt/compiler-explorer

    mkdir -p /opt/intel
    mountpoint /opt/intel || mount --bind /efs/intel /opt/intel

    mkdir -p /opt/arm
    mountpoint /opt/arm || mount --bind /efs/arm /opt/arm

    [ -f /opt/.health ] || touch /opt/.health
    mountpoint /opt/.health || mount --bind /efs/.health /opt/.health
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
    echo "${S3_KEY}" >s3_key
    curl -sL "${URL}" | tar Jxf -
    chown -R ${CE_USER}:${CE_USER} .
    popd
}

update_code() {
    local S3_KEY
    local CUR_S3_KEY=""
    S3_KEY=$(curl -sL "https://s3.amazonaws.com/compiler-explorer/version/${BRANCH}")
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

cgcreate -a ${CE_USER}:${CE_USER} -g memory,pids,cpu,net_cls:ce-sandbox
cgcreate -a ${CE_USER}:${CE_USER} -g memory,pids,cpu,net_cls:ce-compile

mount_opt
rsync_boost
update_code

cd "${DEPLOY_DIR}"
# shellcheck disable=SC2086
exec sudo -u ${CE_USER} -H --preserve-env=NODE_ENV -- \
    /opt/compiler-explorer/node/bin/node \
    -- app.js \
    --suppressConsoleLog \
    --logHost "${LOG_DEST_HOST}" \
    --logPort "${LOG_DEST_PORT}" \
    --env amazon \
    --port 10240 \
    --static out/dist \
    --dist \
    ${EXTRA_ARGS}
