#!/bin/bash

set -ex

. /site.sh

node app.js --env amazon --language go --port 10243 --static out/dist --archivedVersions /opt/gcc-explorer-archive
