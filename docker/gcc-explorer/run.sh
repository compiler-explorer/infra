#!/bin/bash

set -ex

. /site.sh

/update.sh
./node_modules/.bin/supervisor -s -e node,js,properties -w app.js,etc,lib -- app.js --env amazon --port 10240 --lang C++ --static out/dist
