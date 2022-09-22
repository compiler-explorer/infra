#!/usr/bin/env bash
# Sourced when running in beta mode
export BRANCH=beta
export EXTRA_ARGS='--env beta --ensureNoIdClash'
export NODE_ENV=production
