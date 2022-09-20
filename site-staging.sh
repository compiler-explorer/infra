#!/usr/bin/env bash
# Sourced when running in staging mode
export BRANCH=staging
export EXTRA_ARGS='--env staging --ensureNoIdClash'
export NODE_ENV=production
