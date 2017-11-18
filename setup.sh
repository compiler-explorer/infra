#!/bin/bash

set -ex

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

if [[ "$1" != "--updated" ]]; then
    git --work-tree ${DIR} pull
    pwd
    exec bash ${BASH_SOURCE[0]} --updated
    exit 0
fi

${DIR}/setup-common.sh

cp /compiler-explorer-image/init/compiler-explorer.service /lib/systemd/system/compiler-explorer.service
systemctl daemon-reload
systemctl enable compiler-explorer

[ -n "$PACKER_SETUP" ] && exit

docker pull -a mattgodbolt/compiler-explorer
docker pull nginx
