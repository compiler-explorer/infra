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

apt -y install python2.7 python-pip mosh fish
chsh ubuntu -s /usr/bin/fish

cd /home/ubuntu/compiler-explorer-image
pip install -r requirements.txt

sudo -u ubuntu fish setup.fish
