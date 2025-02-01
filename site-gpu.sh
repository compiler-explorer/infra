#!/usr/bin/env bash
# Sourced when running in gpu mode
export BRANCH=gpu
export NODE_ENV=production
export CE_PROP_ENV="${CE_PROP_ENV} --env gpu"

if [ -f /usr/bin/nvidia-modprobe ]; then
  /usr/bin/nvidia-modprobe -c 0
  /usr/bin/nvidia-modprobe -u
  /usr/bin/nvidia-modprobe -l
  /usr/bin/nvidia-modprobe -m
fi
