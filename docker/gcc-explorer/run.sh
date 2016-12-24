#!/bin/bash

set -ex

. /site.sh

export WINEPREFIX=/tmp/wine
mkdir -p ${WINEPREFIX}
# kill any running wineserver...
/opt/wine-devel/bin/wineserver -k || true
# wait for them to die..
/opt/wine-devel/bin/wineserver -w
# start a new one
/opt/wine-devel/bin/wineserver -p
sleep 5 # let it start...
# Run something...
echo "echo It works; exit" | /opt/wine-devel/bin/wine64 cmd
# Hope that that's enough...

./node_modules/.bin/supervisor -s -e node,js,properties -w app.js,etc,lib -- app.js --env amazon --port 10240 --lang C++ --static out/dist --archivedVersions /opt/gcc-explorer-archive

