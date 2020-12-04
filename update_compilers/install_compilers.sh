#!/bin/bash

# This script installs all the free compilers from s3 into a dir in /opt.
# On EC2 this location is on an EFS drive.
ARG1="$1"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.inc
. "${SCRIPT_DIR}/common.inc" "${ARG1}"

echo "Starting installation at $(date), my pid $$"

if install_nightly; then
    echo "Installing nightly builds"
else
    echo "Skipping install of nightly compilers"
fi

ce_install compilers
# at some point, we'll want to do this:
#ce_squash compilers
