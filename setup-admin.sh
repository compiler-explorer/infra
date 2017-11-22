#!/bin/bash

set -ex

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

if [[ "$1" != "--updated" ]]; then
    sudo -u ubuntu git -C ${DIR} pull
    pwd
    exec bash ${BASH_SOURCE[0]} --updated
    exit 0
fi

${DIR}/setup-common.sh

apt -y install python2.7 python-pip

cd /home/ubuntu/compiler-explorer-image
pip install -r requirements.txt
if ! grep compiler-explorer/bin /home/ubuntu/.bashrc; then
    echo PATH=\${PATH}:/home/ubuntu/compiler-explorer/bin >> /home/ubuntu/.bashrc
    chown ubuntu:ubuntu /home/ubuntu/.bashrc
fi
