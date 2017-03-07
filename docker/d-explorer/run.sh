#!/bin/bash

set -ex
. /site.sh

node app.js ${EXTRA_ARGS} --env amazon --language D --port 10241 --static out/dist --archivedVersions /opt/compiler-explorer-archive
