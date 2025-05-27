#!/bin/bash
# Autofs program map for Compiler Explorer squashfs mounts
# This script is called by autofs with the key (path) as $1

set -euo pipefail

# The requested path relative to /opt/compiler-explorer
KEY="$1"

# Base directories
IMG_DIR="/efs/squash-images"
FALLBACK_DIR="/efs/compiler-explorer"

# Check if squashfs image exists
IMG_PATH="${IMG_DIR}/${KEY}.img"

if [[ -f "${IMG_PATH}" ]]; then
    # Squashfs image exists, mount it
    echo "-fstype=squashfs,ro,nodev,relatime :${IMG_PATH}"
else
    # No squashfs, use bind mount to fallback directory
    # Check if the fallback path exists
    FALLBACK_PATH="${FALLBACK_DIR}/${KEY}"

    if [[ -e "${FALLBACK_PATH}" ]]; then
        # Path exists in fallback directory
        echo "-fstype=bind,ro :${FALLBACK_PATH}"
    else
        # Path doesn't exist - return error to autofs
        exit 1
    fi
fi
