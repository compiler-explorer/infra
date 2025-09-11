#!/bin/bash

set -ex

# shellcheck source=start-support.sh
. "${PWD}/start-support.sh"

LOG_DEST_HOST=$(get_conf /compiler-explorer/logDestHostRouter)
LOG_DEST_PORT=$(get_conf /compiler-explorer/logDestPortRouter)

install_ce_router
cd /infra/.deploy

# shellcheck disable=SC2086
exec sudo -u ${CE_USER} -H --preserve-env=NODE_ENV -- \
    env NODE_ENV=production \
    /opt/node/bin/node \
    -- index.js \
    --env "${ENV}" \
    --logHost "${LOG_DEST_HOST}" \
    --logPort "${LOG_DEST_PORT}"
