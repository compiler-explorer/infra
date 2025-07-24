#!/usr/bin/env bash
# Sourced when running in gpu mode
export BRANCH=gpu
export NODE_ENV=production
export CE_PROP_ENV="${CE_PROP_ENV} --env gpu"

# Running `nvidia-smi` is enough to create all the relevant devices
nvidia-smi
