#!/bin/bash

set -ex

export CE_USER=ce
export PATH=$PATH:/home/ubuntu/node/bin

cd /home/ubuntu/ceconan/conanproxy
git pull

npm i -g npm
npm i

CESECRET=$(aws ssm get-parameter --name /compiler-explorer/conanproxysecret | jq -r .Parameter.Value)
CEPASSWORD=$(aws ssm get-parameter --name /compiler-explorer/conanpwd | jq -r .Parameter.Value)
export CESECRET
export CEPASSWORD

sudo -u ce -H /home/${CE_USER}/.local/bin/gunicorn -b 0.0.0.0:9300 -w 4 -t 300 conans.server.server_launcher:app &

# shellcheck disable=SC2086
#  (we deliberately pass multiple args in ${EXTRA_ARGS}
exec sudo -u ce -H --preserve-env=NODE_ENV,PATH,CE_USER,CESECRET,CEPASSWORD -- \
    /home/ubuntu/node/bin/node \
    -- index.js \
    ${EXTRA_ARGS}
