#!/bin/bash

set -exuo pipefail

# NB this is run from the steps in (private) https://github.com/compiler-explorer/ce-ci

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${DIR}"

env EXTRA_NFS_ARGS="" "${DIR}/setup-common.sh" ci

ln -s /efs/squash-images /opt/squash-images
ln -s /efs/wine-stable /opt/wine-stable
# Some things try to canonicalise their installation. Ideally nothing
# would end up building with references to `/opt/compiler-explorer`
# hardcoded in to it, but we have some compilers that do. And some of
# those also the canonicalise the path and end up hardcoding `/efs/...`
# which is the wrong path on the installed machines. So..a hard link here...
ln -d /efs/compiler-explorer /opt/compiler-explorer
