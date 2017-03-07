#!/bin/bash

set -ex
. /site.sh

node app.js ${EXTRA_ARGS} --env amazon --language Rust --port 10242 --static out/dist --archivedVersions /opt/compiler-explorer-archive
