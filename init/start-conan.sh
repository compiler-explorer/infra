#!/bin/bash

set -ex

export CE_USER=ce
export PATH=$PATH:/home/ubuntu/node/bin

cd /home/ubuntu/ceconan/conanproxy
git pull

npm i

CESECRET=$(aws ssm get-parameter --name /compiler-explorer/conanproxysecret | jq -r .Parameter.Value)
CEPASSWORD=$(aws ssm get-parameter --name /compiler-explorer/conanpwd | jq -r .Parameter.Value)
export CESECRET
export CEPASSWORD

# Noble installs gunicorn into a venv; the legacy bionic AMI used a user-local pip install.
GUNICORN=/home/${CE_USER}/venv/bin/gunicorn
[ -x "${GUNICORN}" ] || GUNICORN=/home/${CE_USER}/.local/bin/gunicorn

sudo -u ce -H "${GUNICORN}" -b 0.0.0.0:9300 -w 4 -t 300 conans.server.server_launcher:app &

# shellcheck disable=SC2086
#  (we deliberately pass multiple args in ${EXTRA_ARGS}
exec sudo -u ce -H --preserve-env=NODE_ENV,PATH,CE_USER,CESECRET,CEPASSWORD -- \
    /home/ubuntu/node/bin/node \
    -- index.js \
    ${EXTRA_ARGS}
