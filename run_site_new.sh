#!/bin/bash

set -ex

DIR=$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )
DEPLOY_DIR=${DIR}/.deploy
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
ARCHIVE_DIR=/opt/compiler-explorer-archive
if [[ "${DEV_MODE}" != "prod" ]]; then
    EXTERNAL_PORT=7000
    CONFIG_FILE=${DIR}/site-${DEV_MODE}.sh
fi
. ${CONFIG_FILE}

export GOOGLE_API_KEY

get_from_git() {
    git clone --single-branch --branch ${BRANCH} https://github.com/mattgodbolt/compiler-explorer.git $1
    pushd $1
    local DIST_CMD="env NODE_ENV=development PATH=/opt/compiler-explorer/gdc5.2.0/x86_64-pc-linux-gnu/bin:/opt/compiler-explorer/rust-1.14.0/bin:/opt/compiler-explorer/node/bin:$PATH make -j$(nproc) dist"
    if [[ $UID = 0 ]]; then
        chown -R ubuntu .
        su -c "${DIST_CMD}" ubuntu
    else
        ${DIST_CMD}
    fi
    popd
}

get_released_code() {
    local HASH=$(git ls-remote https://github.com/mattgodbolt/compiler-explorer.git refs/heads/${BRANCH} | awk '{ print $1 }')
    local TEMPFILE=/tmp/ce-release.tar.xz
    aws s3 cp s3://compiler-explorer/dist/${HASH}.tar.xz ${TEMPFILE} || true
    if [[ ! -f ${TEMPFILE} ]]; then
        get_from_git $1
        return
    fi
    mkdir -p $1
    pushd $1
    tar Jxf ${TEMPFILE}
    rm ${TEMPFILE}
    if [[ $UID = 0 ]]; then
        chown -R ubuntu .
    fi
    popd
}

update_code() {
    rm -rf ${DEPLOY_DIR}
    get_released_code ${DEPLOY_DIR}
    CFG="${CFG} -v${DEPLOY_DIR}:/compiler-explorer:ro"
    # Back up the 'v' directory to the long-term archive
    mkdir -p ${ARCHIVE_DIR}
    rsync -av ${DEPLOY_DIR}/out/dist/v/ ${ARCHIVE_DIR}
    CFG="${CFG} -v${ARCHIVE_DIR}:/opt/compiler-explorer-archive:ro"
}

wait_for_ports() {
    for PORT in "$@"; do
        for tensecond in $(seq 15); do
            if curl http://localhost:$PORT/healthcheck > /dev/null 2>&1; then
                echo "Server on port ${PORT} is up and running"
                return
            fi
            sleep 10
        done
        echo "Failed to get port ${PORT}"
        exit 1
    done
}

init_wine() {
    export WINEPREFIX=/tmp/wine
    mkdir -p ${WINEPREFIX}
    # kill any running wineserver...
    /opt/wine-devel/bin/wineserver -k || true
    # wait for them to die..
    /opt/wine-devel/bin/wineserver -w
    # start a new one
    /opt/wine-devel/bin/wineserver -p
    sleep 5 # let it start...
    # Run something...
    echo "echo It works; exit" | /opt/wine-devel/bin/wine64 cmd
    # Hope that that's enough...
}

update_code
init_wine

export LOG_DIR=/tmp/ce-logs
mkdir -p ${LOG_DIR}
cd ${DEPLOY_DIR}
PORTS=

start_server() {
    local LANG=$1
    local PORT=$2
    shift
    shift
    env PATH=/opt/compiler-explorer/bin:${PATH} node ./node_modules/.bin/supervisor -s -e node,js,properties -w app.js,etc,lib -- \
        app.js \
        --env amazon \
        --port ${PORT} \
        --lang ${LANG} \
        --static out/dist \
        --archivedVersions ${ARCHIVE_DIR} \
        "$@" >> ${LOG_DIR}/${LANG}-${PORT}.log 2>&1 &
     PORTS="${PORTS} ${PORT}"
}

trap '$SUDO docker stop nginx' SIGINT SIGTERM SIGPIPE
# TODO: update /etc/log_files.yml to log outputs, or configure outputs directly somehow?
# TODO handle being the "right" user (not ubuntu/root)
# TODO check all the relevant apps work
start_server C++ 10240
start_server D 10241
start_server Rust 10242
start_server C++ 20480 --env cppx
start_server Ispc 20481
start_server Haskell 20482
start_server Swift 20483

wait_for_ports ${PORTS}

$SUDO docker stop nginx || true
$SUDO docker rm nginx || true
$SUDO docker run \
    -p ${EXTERNAL_PORT}:80 \
    --name nginx \
    --network="host" \
    -v /var/log/nginx:/var/log/nginx \
    -v /home/ubuntu:/var/www:ro \
    -v ${DIR}/nginx.conf:/etc/nginx/nginx.conf:ro \
    -v ${DIR}/nginx_new:/etc/nginx/sites-enabled:ro \
    nginx
