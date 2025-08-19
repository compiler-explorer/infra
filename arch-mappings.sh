#!/bin/bash

# Shared architecture mappings for Compiler Explorer infrastructure scripts
# This file should be sourced by setup scripts that need architecture conversions

# dpkg architecture is either amd64 or arm64
ARCH=$(dpkg --print-architecture)

declare -A DPKG_TO_AWS
DPKG_TO_AWS["amd64"]="x86_64"
DPKG_TO_AWS["arm64"]="aarch64"

declare -A DPKG_TO_NODE
DPKG_TO_NODE["amd64"]="x64"
DPKG_TO_NODE["arm64"]="arm64"

# shellcheck disable=SC2034  # Variables used by sourcing scripts
AWS_ARCH="${DPKG_TO_AWS[$ARCH]}"
# shellcheck disable=SC2034
NODE_ARCH="${DPKG_TO_NODE[$ARCH]}"

unset DPKG_TO_AWS
unset DPKG_TO_NODE
