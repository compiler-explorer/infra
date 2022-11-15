#!/usr/bin/env bash
# Sourced when running in gpu mode
export BRANCH=gpu
export NODE_ENV=production
export CE_PROP_ENV=gpu
/infra/setup-gpu-node-devices.sh
