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

# Disable io_uring to work around Linux kernel bug that causes Node.js processes to hang
# indefinitely during high-volume async I/O (like compiler discovery with S3 cache).
# See: https://github.com/nodejs/node/issues/55587
#      https://bugs.launchpad.net/ubuntu/+source/linux/+bug/2105471
export UV_USE_IO_URING=0

# shellcheck disable=SC2086
exec sudo -u ${CE_USER} -H --preserve-env=NODE_ENV,UV_USE_IO_URING -- \
    /opt/node/bin/node \
    -- app.js \
    --discoveryonly=/home/ce/discovered-compilers.json \
    --exit-on-compiler-failure \
    --env amazon \
    --env discovery \
    --port 10240 \
    --metricsPort 10241 \
    --loki "http://127.0.0.1:3500" \
    --static out/dist \
    --dist \
    ${EXTRA_ARGS}
