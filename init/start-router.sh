#!/bin/bash

set -ex

# shellcheck source=start-support.sh
. "${PWD}/start-support.sh"

LOG_DEST_HOST=$(get_conf /compiler-explorer/logDestHostRouter)
LOG_DEST_PORT=$(get_conf /compiler-explorer/logDestPortRouter)

install_ce_router
cd /infra/.deploy

# shellcheck disable=SC2086
# UV_USE_IO_URING=0 works around Linux kernel bug that causes Node.js processes to hang
# indefinitely during high-volume async I/O. See: https://github.com/nodejs/node/issues/55587
exec sudo -u ${CE_USER} -H --preserve-env=NODE_ENV -- \
    env NODE_ENV=production UV_USE_IO_URING=0 \
    /opt/node/bin/node \
    -- index.js \
    --env "${ENV}" \
    --logHost "${LOG_DEST_HOST}" \
    --logPort "${LOG_DEST_PORT}"
