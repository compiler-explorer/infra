#!/bin/bash

set -ex

CE_USER=ce

cd /home/ubuntu/ceconan/conanproxy
git pull

npm i -g npm
npm i

exec sudo -u ${CE_USER} -H --preserve-env=NODE_ENV -- \
    /home/ubuntu/node/bin/node \
    -- index.js \
    --port 80 \
    ${EXTRA_ARGS}
