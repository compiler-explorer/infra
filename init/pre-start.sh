#!/bin/bash

set -e
HOME=/root
mkfifo /tmp/compiler-explorer-log
( logger -t compiler-explorer </tmp/compiler-explorer-log & )
exec >/tmp/compiler-explorer-log
rm /tmp/compiler-explorer-log
cd /compiler-explorer-image
exec ./setup.sh 2>&1
