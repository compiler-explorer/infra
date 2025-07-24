#!/usr/bin/env bash
# Sourced when running in staging mode
export BRANCH=staging
export NODE_ENV=production
export CE_PROP_ENV="${CE_PROP_ENV} --env staging"
