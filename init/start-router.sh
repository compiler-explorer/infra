#!/bin/bash

set -ex

# shellcheck source=start-support.sh
. "${PWD}/start-support.sh"

LOG_DEST_HOST=$(get_conf /compiler-explorer/logDestHostRouter)
LOG_DEST_PORT=$(get_conf /compiler-explorer/logDestPortRouter)

install_ce_router
cd /infra/.deploy

# Get SQS overflow configuration from SSM parameters (with defaults)
SQS_MAX_MESSAGE_SIZE=$(get_conf /compiler-explorer/sqsMaxMessageSize 262144)
S3_OVERFLOW_BUCKET=$(get_conf /compiler-explorer/s3OverflowBucket compiler-explorer-sqs-overflow)
S3_OVERFLOW_KEY_PREFIX=$(get_conf /compiler-explorer/s3OverflowKeyPrefix messages/)

# shellcheck disable=SC2086
exec sudo -u ${CE_USER} -H --preserve-env=NODE_ENV -- \
    env NODE_ENV=production \
    SQS_MAX_MESSAGE_SIZE="${SQS_MAX_MESSAGE_SIZE}" \
    S3_OVERFLOW_BUCKET="${S3_OVERFLOW_BUCKET}" \
    S3_OVERFLOW_KEY_PREFIX="${S3_OVERFLOW_KEY_PREFIX}" \
    /opt/node/bin/node \
    -- index.js \
    --env "${ENV}" \
    --logHost "${LOG_DEST_HOST}" \
    --logPort "${LOG_DEST_PORT}"
