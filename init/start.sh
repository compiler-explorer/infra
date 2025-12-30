#!/bin/bash

set -ex

CE_PROP_ENV="--env amazon"

# shellcheck source=start-support.sh
. "${PWD}/start-support.sh"

LOG_DEST_HOST=$(get_conf /compiler-explorer/logDestHost)
LOG_DEST_PORT=$(get_conf /compiler-explorer/logDestPort)

# Detect instance color for blue-green deployment queue routing
echo "Detecting instance color..."
METADATA_TOKEN=$(curl -s -X PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 21600")
INSTANCE_COLOR=$(curl -s -H "X-aws-ec2-metadata-token: $METADATA_TOKEN" http://169.254.169.254/latest/meta-data/tags/instance/Color 2>/dev/null)
if [[ -n "$INSTANCE_COLOR" ]]; then
    echo "Instance color: $INSTANCE_COLOR"
    INSTANCE_COLOR_ARG="--instance-color ${INSTANCE_COLOR}"
else
    echo "No instance color detected, using legacy queue routing"
    INSTANCE_COLOR_ARG=""
fi

setup_cgroups
mount_opt
mount_nosym
update_code

if ! sudo -u "${CE_USER}" nsjail --config /infra/.deploy/etc/nsjail/compilers-and-tools.cfg -- /bin/bash -c "echo nsjail works"; then
    echo "nsjail is not working, please check the configuration."
    log_cgroups
    exit 1
fi

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

# Disable io_uring to work around Linux kernel bug that causes Node.js processes to hang
# indefinitely during high-volume async I/O (like compiler discovery with S3 cache).
# See: https://github.com/nodejs/node/issues/55587
#      https://bugs.launchpad.net/ubuntu/+source/linux/+bug/2105471
export UV_USE_IO_URING=0

# shellcheck disable=SC2086
exec sudo -u ${CE_USER} -H --preserve-env=NODE_ENV,UV_USE_IO_URING -- \
    /opt/node/bin/node \
    -- app.js \
    --suppress-console-log \
    --tmp-dir /nosym/tmp \
    --log-host "${LOG_DEST_HOST}" \
    --log-port "${LOG_DEST_PORT}" \
    ${CE_PROP_ENV} \
    --port 10240 \
    --metrics-port 10241 \
    --loki "http://127.0.0.1:3500" \
    --dist \
    ${INSTANCE_COLOR_ARG} \
    ${COMPILERS_ARG} \
    ${EXTRA_ARGS}
