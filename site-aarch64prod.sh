#!/usr/bin/env bash
export BRANCH=aarch64prod
export NODE_ENV=production
export CE_PROP_ENV="${CE_PROP_ENV} --env ${BRANCH}"
export SKIP_SQUASH=1
