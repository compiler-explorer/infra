#!/bin/bash

SUDO=sudo
if [[ $UID = 0 ]]; then
    SUDO=
fi

. /compiler-explorer-image/init/shared.sh

echo "Stopping containers"
$SUDO docker stop ${CE_ALL_CONTAINERS} || true

echo "Removing containers"
$SUDO docker rm ${CE_ALL_CONTAINERS} || true

