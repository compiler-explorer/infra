#!/bin/bash

set -ex

. /site.sh

node app.js --env amazon --env amazon1204 --language C++ --port 20480 --static out/dist --archivedVersions /opt/gcc-explorer-archive
