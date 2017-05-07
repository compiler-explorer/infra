#!/bin/bash

set -e
HOME=/root
export HOME
mkfifo /tmp/compiler-explorer-log
( logger -t compiler-explorer </tmp/compiler-explorer-log & )
exec >/tmp/compiler-explorer-log
rm /tmp/compiler-explorer-log
cd /compiler-explorer-image
exec ./run_site.sh prod 2>&1
