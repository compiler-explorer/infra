#!/bin/bash

set -ex
. /site.sh

node app.js --env amazon --language Rust --port 10242 --static out/dist --archivedVersions /opt/compiler-explorer-archive ${EXTRA_ARGS}
