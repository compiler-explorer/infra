#!/bin/bash

set -ex

. /site.sh

node app.js ${EXTRA_ARGS} --env amazon --env amazon1204 --language C++ --port 20480 --static out/dist --archivedVersions /opt/compiler-explorer-archive
