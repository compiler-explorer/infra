#!/bin/bash

set -ex
. /site.sh

node app.js --env amazon --language rust --port 10242 --static out/dist --archivedVersions /opt/gcc-explorer-archive
