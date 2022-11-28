#!/usr/bin/env bash
# Sourced when running in beta mode
export BRANCH=beta
export CE_PROP_ENV="${CE_PROP_ENV} --env beta"
export NODE_ENV=production
