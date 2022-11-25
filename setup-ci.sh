#!/bin/bash

set -exuo pipefail

# NB this is run from the steps in (private) https://github.com/compiler-explorer/ce-ci

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${DIR}"

env EXTRA_NFS_ARGS="" "${DIR}/setup-common.sh" ci

ln -s /efs/squash-images /opt/squash-images
ln -s /efs/compiler-explorer /opt/compiler-explorer
ln -s /efs/wine-stable /opt/wine-stable
