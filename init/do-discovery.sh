#!/bin/bash

set -ex

# shellcheck source=start-support.sh
. "${PWD}/start-support.sh"

setup_cgroups
update_code

sudo rm -Rf /tmp/ce-wine-prefix

cd "${DEPLOY_DIR}"

# ensure we can read the results of the discovery...
sudo chmod og+rx /home/ce

# shellcheck disable=SC2086
exec sudo -u ${CE_USER} -H --preserve-env=NODE_ENV -- \
    /opt/node/bin/node \
    -- app.js \
    --discoveryonly=/home/ce/discovered-compilers.json \
    --env amazon \
    --env discovery \
    --port 10240 \
    --metricsPort 10241 \
    --loki "http://127.0.0.1:3500" \
    --static out/dist \
    --dist \
    ${EXTRA_ARGS}
