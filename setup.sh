#!/bin/bash

set -ex

ENV=$(curl -sf http://169.254.169.254/latest/user-data | tr A-Z a-z || true)
ENV=${ENV:-prod}
BRANCH=master
if [[ "$ENV" = "beta" ]]; then
BRANCH=beta
fi
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

if [[ "$1" != "--updated" || "$2" != "${BRANCH}" ]]; then
    git --work-tree ${DIR} checkout ${BRANCH}
    git --work-tree ${DIR} pull
    exec bash ${BASH_SOURCE[0]} --updated ${BRANCH}
    exit 0
fi

EXTRA_NFS_ARGS=",ro"
${DIR}/setup-common.sh

cp /compiler-explorer-image/init/compiler-explorer.service /lib/systemd/system/compiler-explorer.service
systemctl daemon-reload
systemctl enable compiler-explorer

[ -n "$PACKER_SETUP" ] && exit

docker pull -a mattgodbolt/compiler-explorer
docker pull nginx
