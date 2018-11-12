#!/bin/bash

SUDO=sudo
if [[ $UID = 0 ]]; then
    SUDO=
fi

. /compiler-explorer-image/init/shared.sh

$SUDO docker stop ${CE_ALL_CONTAINERS} || true
$SUDO docker rm ${CE_ALL_CONTAINERS} || true
