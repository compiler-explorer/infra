#!/bin/bash

set -ex
. /site.sh

/update.sh

node app.js --env amazon --language d --port 10241 --static out/dist
