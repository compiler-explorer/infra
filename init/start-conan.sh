#!/bin/bash

set -ex

CE_USER=ce

cd /home/ubuntu/ceconan/conanproxy
git pull

npm i -g npm
npm i

sudo -u ce /home/${CE_USER}/.local/bin/gunicorn -b 0.0.0.0:9300 -w 4 -t 300 conans.server.server_launcher:app &

exec sudo -u ${CE_USER} -H --preserve-env=NODE_ENV -- \
    /home/ubuntu/node/bin/node \
    -- index.js \
    --port 80 \
    ${EXTRA_ARGS}
