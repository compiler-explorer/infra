#!/bin/bash

set -ex

CE_PROP_ENV="--env amazon"

# shellcheck source=start-support.sh
. "${PWD}/start-support.sh"

LOG_DEST_HOST=$(get_conf /compiler-explorer/logDestHost)
LOG_DEST_PORT=$(get_conf /compiler-explorer/logDestPort)

setup_cgroups
mount_opt
update_code

COMPILERS_ARG=
if [[ -f "${COMPILERS_FILE}" ]]; then
    COMPILERS_ARG="--prediscovered=${COMPILERS_FILE}"
fi

install_asmparser
install_ninja

cd "${DEPLOY_DIR}"

if [[ "${ENV}" == "runner" ]]; then
  exit
fi

# shellcheck disable=SC2086
exec sudo -u ${CE_USER} -H --preserve-env=NODE_ENV -- \
    /opt/node/bin/node \
    -- app.js \
    --suppressConsoleLog \
    --logHost "${LOG_DEST_HOST}" \
    --logPort "${LOG_DEST_PORT}" \
    ${CE_PROP_ENV} \
    --port 10240 \
    --metricsPort 10241 \
    --loki "http://127.0.0.1:3500" \
    --dist \
    ${COMPILERS_ARG} \
    ${EXTRA_ARGS}
