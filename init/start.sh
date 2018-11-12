#!/bin/bash

set -e
HOME=/root
export HOME
mkfifo /tmp/compiler-explorer-log
( logger -t compiler-explorer </tmp/compiler-explorer-log & )
exec >/tmp/compiler-explorer-log
rm /tmp/compiler-explorer-log
cd /compiler-explorer-image
ENV=$(curl -sf http://169.254.169.254/latest/user-data || true)
ENV=${ENV:-prod}
echo Running in environment ${ENV}
. /compiler-explorer-image/init/shared.sh
exec ./run_site.sh ${ENV} 2>&1
