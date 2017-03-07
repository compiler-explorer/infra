#!/bin/bash

set -ex

. /site.sh

node app.js ${EXTRA_ARGS} --env amazon --language Go --port 10243 --static out/dist --archivedVersions /opt/compiler-explorer-archive
